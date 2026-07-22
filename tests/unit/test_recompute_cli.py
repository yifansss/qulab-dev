from qulab.analysis.recompute import _parse_set, main


def test_set_parser_is_yaml_safe_not_eval():
    assert _parse_set(["scale=2", "window=[1e-6, 3e-6]"]) == {"scale": 2, "window": [1e-6, 3e-6]}


def test_cli_missing_run_returns_data_error(tmp_path):
    assert main(["--run", str(tmp_path / "missing"), "--module", "m", "--dry-run"]) == 3
