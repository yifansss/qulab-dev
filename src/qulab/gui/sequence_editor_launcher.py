"""Launcher for the standalone sequence editor with file handoff support."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: sequence_editor_launcher.py EDITOR_PATH [SEQUENCE_PATH]", file=sys.stderr)
        return 2
    editor_path = Path(args[0]).expanduser().resolve()
    sequence_path = Path(args[1]).expanduser().resolve() if len(args) > 1 and args[1] else None

    module = _load_editor_module(editor_path)
    app = module.QApplication.instance() or module.QApplication(sys.argv)
    dialog = module.EditSequenceDialog()
    if sequence_path is not None:
        _load_sequence_into_dialog(module, dialog, sequence_path)
    result = dialog.exec_()
    if result == module.QDialog.Accepted:
        print(json.dumps(dialog.get_params(), indent=2, ensure_ascii=False), flush=True)
    app.processEvents()
    return 0


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
