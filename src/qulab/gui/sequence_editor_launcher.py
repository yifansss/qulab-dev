"""Launcher for the standalone sequence editor with file handoff support."""

from __future__ import annotations

import importlib.util
import json
import sys
import hashlib
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: sequence_editor_launcher.py EDITOR_PATH [SEQUENCE_PATH]", file=sys.stderr)
        return 2
    editor_path = Path(args[0]).expanduser().resolve()
    sequence_path = Path(args[1]).expanduser().resolve() if len(args) > 1 and args[1] else None

    with redirect_stdout(sys.stderr):
        module = _load_editor_module(editor_path)
        app = module.QApplication.instance() or module.QApplication(sys.argv)
        dialog = module.EditSequenceDialog()
        if sequence_path is not None:
            _load_sequence_into_dialog(module, dialog, sequence_path)
        result = dialog.exec_()
        params = dialog.get_params() if result == module.QDialog.Accepted else []
    saved = None
    if result == module.QDialog.Accepted:
        active_path = str(getattr(dialog, "active_file", "")).strip()
        target = Path(active_path) if active_path else sequence_path
        if target is not None:
            saved = _write_sequence_artifact(target, params)
    pulse_count = sum(len(ch.get("pulses", [])) for ch in params if isinstance(ch, dict))
    payload = {"protocol_version": 1, "editor_version": "1", "capabilities": ["open", "edit_channels", "edit_pulses", "validate", "preview", "save"],
               "source": None if sequence_path is None else str(sequence_path), "dirty": result != module.QDialog.Accepted,
               "validation": [], "summary": {"channels": [ch.get("channel_name") for ch in params if isinstance(ch, dict)], "pulse_count": pulse_count, "duration_s": None},
               "saved_artifact": saved}
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")), flush=True)
    app.processEvents()
    return 0


def _write_sequence_artifact(path: Path, params: Any) -> dict[str, str]:
    """Persist only editor pulse data; protocol data is stdout-only."""
    if not isinstance(params, list):
        raise RuntimeError("Sequence editor returned invalid pulse data; expected a channel list.")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(params, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _load_editor_module(editor_path: Path):
    spec = importlib.util.spec_from_file_location("qulab_external_sequence_editor", editor_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load sequence editor: {editor_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_sequence_into_dialog(module, dialog, sequence_path: Path) -> None:
    if sequence_path.exists():
        with sequence_path.open("r", encoding="utf-8") as handle:
            params = json.load(handle)
        dialog.load_params(module.adapt_legacy_sequence(params))
    dialog.active_file = str(sequence_path)


if __name__ == "__main__":
    raise SystemExit(main())
