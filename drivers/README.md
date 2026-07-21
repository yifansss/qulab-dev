# Drivers

`drivers/pycontrol/` contains the vendored instrument driver tree used by Qulab
hardware adapters. It was copied from the previous sibling project layout so
the lab can move this Qulab project to another computer without relying on
external relative paths.

Adapter import priority:

1. resource-level `pycontrol_path`
2. `QULAB_PYCONTROL_PATH`
3. project-local `drivers/pycontrol`

Relative paths are resolved from the Qulab project root first. Use an absolute
path or `QULAB_PYCONTROL_PATH` only when intentionally testing a different
driver tree.

The adapters still import drivers only during `connect()`, so normal dry-run,
GUI import, and pytest paths remain hardware-free.
