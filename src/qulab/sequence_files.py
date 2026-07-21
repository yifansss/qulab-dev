"""Sequence file discovery and run artifact helpers."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from qulab.paths import resolve_project_path


@dataclass(frozen=True)
class SequenceFileInfo:
    path: str
    exists: bool
    mtime: float | None
    size_bytes: int | None
    sha256: str | None
    parameters: list[str] = field(default_factory=list)
    channels: list[str] = field(default_factory=list)
    preview_lines: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SequenceReference:
    reference_id: str
    label: str
    source: str
    resource: str
    sequence_file: str
    config_path: tuple[str | int, ...]


def inspect_sequence_file(path: str | Path | None) -> SequenceFileInfo:
    raw_path = "" if path is None else str(path)
    warnings: list[str] = []
    if not raw_path.strip():
        return SequenceFileInfo(raw_path, False, None, None, None, warnings=["No sequence_file configured."])
    sequence_path = resolve_project_path(raw_path)
    if sequence_path is None:
        return SequenceFileInfo(raw_path, False, None, None, None, warnings=[f"Sequence file path is empty: {raw_path}"])
    try:
        stat = sequence_path.stat()
    except FileNotFoundError:
        return SequenceFileInfo(
            raw_path,
            False,
            None,
            None,
            None,
            warnings=[f"Sequence file not found: {raw_path}"],
        )
    except OSError as exc:
        return SequenceFileInfo(raw_path, False, None, None, None, warnings=[f"Cannot inspect sequence file: {exc}"])
    sha256 = _sha256(sequence_path)
    parameters: list[str] = []
    channels: list[str] = []
    preview_lines: list[str] = []
    try:
        text = sequence_path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        warnings.append(f"Cannot read sequence file text for metadata: {exc}")
    else:
        parameters = _parse_parameter_names(text)
        channels = _parse_channels(text)
        preview_lines = _parse_sequence_preview(text)
    if not parameters:
        warnings.append("No scan parameters detected in sequence file.")
    if not channels:
        warnings.append("No channel mapping detected in sequence file.")
    warnings.append("Estimated sequence duration is unknown.")
    return SequenceFileInfo(
        raw_path,
        True,
        stat.st_mtime,
        stat.st_size,
        sha256,
        parameters,
        channels,
        preview_lines,
        warnings,
    )


def discover_sequence_references(config: dict[str, Any]) -> list[SequenceReference]:
    references: list[SequenceReference] = []
    resources = config.get("resources", {})
    if isinstance(resources, dict):
        for name, resource in resources.items():
            if isinstance(resource, dict) and resource.get("sequence_file"):
                references.append(
                    SequenceReference(
                        reference_id=_safe_id(f"resource_{name}"),
                        label=f"{name} resource sequence",
                        source=f"resources.{name}.sequence_file",
                        resource=str(name),
                        sequence_file=str(resource["sequence_file"]),
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
            target = artifact_dir / f"{reference.reference_id}_{info.sha256[:12]}{suffix}"
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
                "preview_lines": info.preview_lines,
                "warnings": info.warnings,
            }
        )
    return snapshots


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


def _parse_sequence_preview(text: str) -> list[str]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    lines: list[str] = []
    for index, channel in enumerate(data, start=1):
        if not isinstance(channel, dict):
            continue
        name = str(channel.get("channel_name") or f"Channel {index}")
        pulses = channel.get("pulses") if isinstance(channel.get("pulses"), list) else []
        starts = []
        for pulse in pulses[:4]:
            if isinstance(pulse, dict) and "start_time" in pulse:
                starts.append(str(pulse["start_time"]))
        suffix = f", starts: {', '.join(starts)}" if starts else ""
        lines.append(f"{name}: {len(pulses)} pulse(s){suffix}")
    return lines


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
