from pathlib import Path

import pytest

from qulab.analysis import AnalysisError, AnalysisModuleRegistry, load_analysis_plan


def test_dotted_class_load_and_source_hash():
    plan, issues = load_analysis_plan({"modules": [{"name": "scale", "module": "analysis_modules.examples.passthrough_scale",
        "class": "PassthroughScale", "inputs": ["source_value"], "outputs": ["scaled_value"]}]})
    assert not issues
    item = plan.modules[0]
    assert len(item.source_identity.sha256) == 64
    runtime = AnalysisModuleRegistry().instantiate(item)
    assert runtime.version == "1"


def test_project_relative_file_load_independent_of_cwd(tmp_path, monkeypatch):
    module_path = tmp_path / "custom.py"
    module_path.write_text("class Mod:\n name='m'\n version='2'\n input_keys=('x',)\n output_keys=('y',)\n def setup(self, config, run_context): pass\n def process_point(self, point): return {'y': 1}\n def close(self): pass\n")
    monkeypatch.chdir(Path("/"))
    plan, issues = load_analysis_plan({"modules": [{"name": "custom", "module": "custom.py", "class": "Mod",
                                                    "inputs": ["x"], "outputs": ["y"]}]}, project_base=tmp_path)
    assert not issues
    assert plan.modules[0].source_identity.version == "2"
    assert AnalysisModuleRegistry().instantiate(plan.modules[0]).name == "m"


def test_missing_object_has_stable_issue():
    _, issues = load_analysis_plan({"modules": [{"name": "bad", "module": "analysis_modules.examples.passthrough_scale",
                                                 "class": "Missing", "inputs": ["x"], "outputs": ["y"]}]})
    assert issues[0].code == "analysis_object_not_found"
