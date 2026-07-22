from qulab.analysis import load_analysis_plan


def module(**changes):
    value = {"name": "scale_preview", "module": "analysis_modules.examples.passthrough_scale",
             "class": "PassthroughScale", "inputs": ["source_value"], "outputs": ["scaled_value"],
             "args": {}}
    value.update(changes)
    return value


def test_absent_and_defaults():
    assert load_analysis_plan(None) == (None, [])
    plan, issues = load_analysis_plan({"modules": [module()]})
    assert not issues
    assert plan.live.enabled is False
    assert plan.modules[0].save is True
    assert plan.modules[0].args == {"scale": 1.0}


def test_namespace_and_live_only_warning():
    plan, issues = load_analysis_plan({"live": {"enabled": True}, "modules": [module(namespace="preview", show=True, save=False)]})
    assert plan.modules[0].effective_outputs == ("preview.scaled_value",)
    assert any(issue.code == "analysis_live_only_output" for issue in issues)


def test_invalid_policy_and_class_function():
    _, issues = load_analysis_plan({"live": {"fail_policy": "explode"},
                                    "modules": [module(function="compute")]})
    assert {issue.code for issue in issues} >= {"analysis_fail_policy_invalid", "analysis_config_invalid"}
