"""Project-local path helpers.

Runtime entry points may be launched from a terminal, a GUI shortcut, or a
different working directory. These helpers keep config-relative files anchored
to the Qulab project tree first so experiments are portable across computers.
"""

from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_project_path(
    path: str | Path | None,
    *,
    base_dir: str | Path | None = None,
    must_exist: bool = False,
) -> Path | None:
    if path is None:
        return None
    text = str(path).strip()
    if not text:
        return None
    raw = Path(os.path.expandvars(text)).expanduser()
    if raw.is_absolute():
        return raw.resolve() if raw.exists() else raw

    candidates: list[Path] = [(project_root() / raw).resolve()]
    if base_dir is not None:
        candidates.append((Path(base_dir).expanduser() / raw).resolve())
    candidates.append((Path.cwd() / raw).resolve())

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None if must_exist else candidates[0]


def project_relative(path: str | Path | None) -> str:
    resolved = resolve_project_path(path)
    if resolved is None:
        return ""
    try:
        return str(resolved.relative_to(project_root()))
    except ValueError:
        return str(resolved)
