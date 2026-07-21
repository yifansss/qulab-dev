"""Import-safe bridge helpers for ASG sequence files and editor launching."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from qulab.paths import project_root as qulab_project_root, resolve_project_path


@dataclass(frozen=True)
class SequenceFileInfo:
    path: str
    exists: bool
    mtime: float | None
    size_bytes: int | None
    sha256: str | None
    parameters: list[str] = field(default_factory=list)
    channels: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SequenceEditorLaunchResult:
    ok: bool
    editor_path: str
    sequence_path: str | None
    message: str
    pid: int | None = None
    process: Any = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class SequenceReference:
    reference_id: str
    label: str
    source: str
    resource: str
    sequence_file: str
    config_path: tuple[str | int, ...]


def default_sequence_editor_path(project_root: Path | None = None) -> Path:
    """Return the project-local standalone ASG sequence editor path."""

    env_path = os.environ.get("QULAB_SEQUENCE_EDITOR_PATH")
    if env_path:
        resolved = resolve_project_path(env_path)
        if resolved is not None:
            return resolved
    root = project_root or qulab_project_root()
    candidates = (
        root / "tools" / "sequence_editor" / "sequence_editor.py",
        root / "sequence_editor" / "sequence_editor.py",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def sequence_editor_launcher_path() -> Path:
    return Path(__file__).with_name("sequence_editor_launcher.py")


def inspect_sequence_file(path: str | Path | None) -> SequenceFileInfo:
    """Inspect a sequence file without importing Qt or hardware drivers."""

    raw_path = "" if path is None else str(path)
    warnings: list[str] = []
    if not raw_path.strip():
        return SequenceFileInfo(
            path=raw_path,
            exists=False,
            mtime=None,
            size_bytes=None,
            sha256=None,
            warnings=["No sequence_file configured."],
        )

    sequence_path = resolve_project_path(raw_path)
    if sequence_path is None:
        return SequenceFileInfo(
            path=raw_path,
            exists=False,
            mtime=None,
            size_bytes=None,
            sha256=None,
            warnings=[f"Sequence file path is empty: {raw_path}"],
        )
    try:
        stat = sequence_path.stat()
    except FileNotFoundError:
        return SequenceFileInfo(
            path=raw_path,
            exists=False,
            mtime=None,
            size_bytes=None,
            sha256=None,
            warnings=[f"Sequence file not found: {raw_path}"],
        )
    except OSError as exc:
        return SequenceFileInfo(
            path=raw_path,
            exists=False,
            mtime=None,
            size_bytes=None,
            sha256=None,
            warnings=[f"Cannot inspect sequence file: {exc}"],
        )

    sha256 = _sha256(sequence_path)
    parameters: list[str] = []
    channels: list[str] = []
    try:
        text = sequence_path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        warnings.append(f"Cannot read sequence file text for metadata: {exc}")
    else:
        parameters = _parse_parameter_names(text)
        channels = _parse_channels(text)

    if not parameters:
        warnings.append("No scan parameters detected in sequence file.")
    if not channels:
        warnings.append("No channel mapping detected in sequence file.")
    warnings.append("Estimated sequence duration is unknown.")
    return SequenceFileInfo(
        path=raw_path,
        exists=True,
        mtime=stat.st_mtime,
        size_bytes=stat.st_size,
        sha256=sha256,
        parameters=parameters,
        channels=channels,
        warnings=warnings,
    )


def discover_sequence_references(config: dict[str, Any]) -> list[SequenceReference]:
    references: list[SequenceReference] = []
    resources = config.get("resources", {})
    if isinstance(resources, dict):
        for name, resource in resources.items():
            if not isinstance(resource, dict):
                continue
            sequence_file = resource.get("sequence_file")
            if sequence_file:
                references.append(
                    SequenceReference(
                        reference_id=_safe_id(f"resource_{name}"),
                        label=f"{name} resource sequence",
                        source=f"resources.{name}.sequence_file",
                        resource=str(name),
                        sequence_file=str(sequence_file),
                        config_path=("resources", str(name), "sequence_file"),
                    )
                )
    for path, step, section in _iter_call_steps(config):
        action = str(step.get("call") or "")
        resource, _, method = action.partition(".")
        if method != "load_sequence" or "asg" not in resource.lower():
            continue
        args = step.get("args")
        if not isinstance(args, dict):
            continue
        sequence_file = _sequence_file_from_args(args)
        if not sequence_file:
            continue
        path_id = _safe_id("_".join(str(part) for part in path))
        references.append(
            SequenceReference(
                reference_id=_safe_id(f"{section}_{path_id}_{resource}_load_sequence"),
                label=f"{resource}.load_sequence at {'/'.join(str(part) for part in path)}",
                source=f"{section}.call[{action}@{'/'.join(str(part) for part in path)}].args.sequence_file",
                resource=resource,
                sequence_file=str(sequence_file),
                config_path=(*path, "args", "sequence_file"),
            )
        )
    return _dedupe_references(references)


def sequence_artifact_snapshots(config: dict[str, Any], run_path: Path | str) -> list[dict[str, Any]]:
    run_dir = Path(run_path)
    artifact_dir = run_dir / "artifacts" / "sequences"
    snapshots: list[dict[str, Any]] = []
    for reference in discover_sequence_references(config):
        info = inspect_sequence_file(reference.sequence_file)
        artifact_path: str | None = None
        if info.exists and info.sha256:
            artifact_dir.mkdir(parents=True, exist_ok=True)
            source_path = resolve_project_path(reference.sequence_file)
            if source_path is None:
                continue
            suffix = source_path.suffix or ".json"
            filename = f"{reference.reference_id}_{info.sha256[:12]}{suffix}"
            target = artifact_dir / filename
            shutil.copy2(source_path, target)
            artifact_path = str(target.relative_to(run_dir))
        snapshots.append(
            {
                "reference_id": reference.reference_id,
                "label": reference.label,
                "source": reference.source,
                "resource": reference.resource,
                "source_path": reference.sequence_file,
                "artifact_path": artifact_path,
                "exists": info.exists,
                "mtime": info.mtime,
                "size_bytes": info.size_bytes,
                "sha256": info.sha256,
                "parameters": info.parameters,
                "channels": info.channels,
                "warnings": info.warnings,
            }
        )
    return snapshots


def open_sequence_editor(
    editor_path: str | Path,
    sequence_path: str | Path | None = None,
    popen_factory: Callable[..., Any] = subprocess.Popen,
    python_executable: str | Path | None = None,
    import_check: Callable[[str, str], "_ImportCheck"] = None,
    capture_output: bool = False,
) -> SequenceEditorLaunchResult:
    """Launch the standalone sequence editor through a monkeypatchable wrapper."""

    editor = resolve_project_path(editor_path) or Path(str(editor_path)).expanduser()
    sequence_resolved = resolve_project_path(sequence_path) if sequence_path is not None else None
    sequence = None if sequence_resolved is None else str(sequence_resolved)
    python = str(python_executable or os.environ.get("QULAB_SEQUENCE_EDITOR_PYTHON") or sys.executable)
    if not str(editor_path).strip():
        return SequenceEditorLaunchResult(False, str(editor_path), sequence, "No sequence editor path configured.")
    if not editor.exists():
        return SequenceEditorLaunchResult(False, str(editor), sequence, f"Sequence editor not found: {editor}")
    if not editor.is_file():
        return SequenceEditorLaunchResult(False, str(editor), sequence, f"Sequence editor is not a file: {editor}")

    check_import = import_check or _check_python_import
    pyqt5_check = check_import(python, "PyQt5")
    if not pyqt5_check.ok:
        return SequenceEditorLaunchResult(
            False,
            str(editor),
            sequence,
            (
                "Sequence editor requires PyQt5, but PyQt5 is not importable in "
                f"{python}. Install PyQt5 in that environment or configure a Python executable that has it."
            ),
        )

    launcher = sequence_editor_launcher_path()
    command = [python, str(launcher), str(editor)]
    if sequence:
        command.append(sequence)
    try:
        kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "text": True} if capture_output else {}
        process = popen_factory(command, **kwargs)
    except Exception as exc:  # pragma: no cover - exact subprocess exceptions are platform specific
        return SequenceEditorLaunchResult(False, str(editor), sequence, f"Failed to launch sequence editor: {exc}")
    return SequenceEditorLaunchResult(
        True,
        str(editor),
        sequence,
        "Sequence editor launched.",
        getattr(process, "pid", None),
        process,
    )


@dataclass(frozen=True)
class _ImportCheck:
    ok: bool
    message: str = ""


def _check_python_import(python: str, module_name: str) -> _ImportCheck:
    command = [python, "-c", f"import {module_name}"]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=5, check=False)
    except Exception as exc:
        return _ImportCheck(False, str(exc))
    if result.returncode == 0:
        return _ImportCheck(True)
    return _ImportCheck(False, (result.stderr or result.stdout).strip())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_parameter_names(text: str) -> list[str]:
    names = set(re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", text))
    names.update(match.group(1) for match in re.finditer(r"\bparam(?:eter)?\s*[:=]\s*([A-Za-z_][A-Za-z0-9_]*)", text))
    return sorted(names)


def _parse_channels(text: str) -> list[str]:
    channels = set()
    for match in re.finditer(r"\b(?:ch|channel)[_\-\s]*(\d+)\b", text, flags=re.IGNORECASE):
        channels.add(f"ch{match.group(1)}")
    return sorted(channels, key=lambda name: int(name[2:]))


def _iter_call_steps(config: dict[str, Any]):
    for section in ("setup", "procedure", "cleanup"):
        steps = config.get(section, [])
        if isinstance(steps, list):
            yield from _walk_steps(steps, (section,), section)


def _walk_steps(steps: list[Any], path: tuple[str | int, ...], section: str):
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        step_path = (*path, index)
        if "call" in step:
            yield step_path, step, section
        for kind in ("scan", "average", "measurement"):
            payload = step.get(kind)
            if isinstance(payload, dict) and isinstance(payload.get("body"), list):
                yield from _walk_steps(payload["body"], (*step_path, kind, "body"), section)
        run = step.get("run")
        if isinstance(run, dict):
            child_steps = run.get("steps", run.get("body", []))
            if isinstance(child_steps, list):
                yield from _walk_steps(child_steps, (*step_path, "run", "steps"), section)


def _sequence_file_from_args(args: dict[str, Any]) -> Any:
    for key in ("sequence_file", "path", "sequence_path"):
        if args.get(key):
            return args[key]
    return None


def _safe_id(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip()).strip("._-")
    return normalized or "sequence"


def _dedupe_references(references: list[SequenceReference]) -> list[SequenceReference]:
    counts: dict[str, int] = {}
    output: list[SequenceReference] = []
    for reference in references:
        count = counts.get(reference.reference_id, 0)
        counts[reference.reference_id] = count + 1
        if count == 0:
            output.append(reference)
        else:
            output.append(
                SequenceReference(
                    reference_id=f"{reference.reference_id}_{count + 1}",
                    label=reference.label,
                    source=reference.source,
                    resource=reference.resource,
                    sequence_file=reference.sequence_file,
                    config_path=reference.config_path,
                )
            )
    return output
