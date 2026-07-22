from pathlib import Path

from qulab.config import validate_config_candidate
from qulab.gui.controller import OperatorController


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_yaml_syntax_and_duplicate_locations(tmp_path: Path) -> None:
    syntax = validate_config_candidate(_write(tmp_path / "syntax.yaml", "procedure:\n  - call: [\n"))
    assert syntax.errors[0].code == "yaml_syntax_error"
    assert syntax.errors[0].line == 3
    assert syntax.errors[0].column is not None

    duplicate = validate_config_candidate(_write(tmp_path / "duplicate.yaml", "name: first\nname: second\nresources: {}\n"))
    issue = next(item for item in duplicate.errors if item.code == "yaml_duplicate_key")
    assert issue.config_path == ("name",)
    assert issue.line == 2


def test_collects_structure_reference_and_nested_source_diagnostics(tmp_path: Path) -> None:
    result = validate_config_candidate(_write(tmp_path / "many.yaml", """
resources:
  bad: {}
procedure:
  - scan:
      name: x
      values: []
      body:
        - call: missing.read
          args: {value: "${unknown}"}
  - average: {count: 0, body: []}
  - wait: 0
"""))
    codes = {item.code for item in result.errors}
    assert {"resource_missing_adapter", "workflow_value_invalid", "action_resource_unknown", "parameter_reference_unresolved"} <= codes
    nested = next(item for item in result.errors if item.code == "parameter_reference_unresolved")
    assert nested.line == 10
    assert nested.workflow_path is not None


def test_invalid_candidate_preserves_active_and_first_failure_has_no_active(tmp_path: Path) -> None:
    valid = _write(tmp_path / "valid.yaml", "name: valid\nresources: {}\nprocedure: []\n")
    invalid = _write(tmp_path / "invalid.yaml", "name: bad\nprocedure: nope\n")
    controller = OperatorController(tmp_path / "runs")
    assert controller.load_config(valid).activated
    active = controller.current_config
    blocked = controller.load_config(invalid)
    assert not blocked.activated
    assert controller.current_config == active
    assert controller.config_path == valid

    fresh = OperatorController(tmp_path / "runs2")
    assert not fresh.load_config(invalid).activated
    assert not fresh.has_active_config


def test_warning_candidate_activates_and_optional_sections_are_valid(tmp_path: Path) -> None:
    result = OperatorController(tmp_path / "runs").load_config(
        _write(tmp_path / "warning.yaml", "name: warning\nresources: {}\nprocedure:\n  - run: {name: r, steps: []}\n")
    )
    assert result.activated
    assert any(item.code == "sync_missing" for item in result.warnings)
