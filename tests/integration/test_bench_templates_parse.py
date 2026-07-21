from pathlib import Path

from qulab.config import load_yaml_config, parse_experiment_config
from qulab.sequence_generation import prepare_and_parse_experiment_config


ROOT = Path(__file__).resolve().parents[2]


def test_bench_templates_parse_and_preflight(tmp_path) -> None:
    paths = sorted((ROOT / "configs" / "experiments").glob("bench_*.template.yaml"))
    assert paths
    for path in paths:
        config = load_yaml_config(path)
        parsed = (
            prepare_and_parse_experiment_config(config, cache_root=tmp_path / path.stem)
            if config.get("sequence_plans")
            else parse_experiment_config(config)
        )

        assert parsed.validation.ok, (path.name, parsed.validation.issues)
        assert parsed.name == config["name"]
