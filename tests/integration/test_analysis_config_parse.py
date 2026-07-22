import yaml

from qulab.config import parse_experiment_config


def test_analysis_and_sequence_compatible_parse():
    config = yaml.safe_load("""
name: analysis_parse
resources: {}
procedure:
  - call: mock.read
    save_as: source_value
analysis:
  live:
    enabled: true
  modules:
    - name: scale_preview
      module: analysis_modules.examples.passthrough_scale
      class: PassthroughScale
      inputs: [source_value]
      outputs: [scaled_value]
      args: {scale: 2}
""")
    parsed = parse_experiment_config(config)
    assert parsed.analysis_plan.modules[0].effective_outputs == ("scaled_value",)
    assert parsed.validation.ok
    yaml.safe_dump(parsed.analysis_plan.to_dict())


def test_old_config_keeps_none_plan():
    parsed = parse_experiment_config({"name": "old", "resources": {}, "procedure": []})
    assert parsed.analysis_plan is None
