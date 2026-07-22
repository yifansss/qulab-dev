from qulab.analysis import load_analysis_plan


def item(name, inputs, outputs, **extra):
    value = {"name": name, "module": "analysis_modules.examples.passthrough_scale", "class": "PassthroughScale",
             "inputs": inputs, "outputs": outputs}
    value.update(extra)
    return value


def test_dependency_order_uses_effective_outputs(tmp_path):
    path = tmp_path / "mods.py"
    path.write_text("class A:\n version='1'\n name='a'\n input_keys=('raw',)\n output_keys=('mid',)\n setup=lambda *a:None\n process_point=lambda *a:None\n close=lambda *a:None\nclass B:\n version='1'\n name='b'\n input_keys=('mid',)\n output_keys=('out',)\n setup=lambda *a:None\n process_point=lambda *a:None\n close=lambda *a:None\n")
    modules = [{"name": "second", "module": str(path), "class": "B", "inputs": ["mid"], "outputs": ["out"]},
               {"name": "first", "module": str(path), "class": "A", "inputs": ["raw"], "outputs": ["mid"]}]
    plan, issues = load_analysis_plan({"modules": modules}, known_raw_keys={"raw"})
    assert not issues
    assert [m.instance_name for m in plan.modules] == ["first", "second"]
    assert plan.dependency_edges == (("first", "second"),)


def test_collisions_and_disabled_dependency(tmp_path):
    path = tmp_path / "mods.py"
    path.write_text("class A:\n version='1'\n name='a'\n input_keys=('x',)\n output_keys=('y',)\n setup=lambda *a:None\n process_point=lambda *a:None\n close=lambda *a:None\n")
    base = {"name": "one", "module": str(path), "class": "A", "inputs": ["x"], "outputs": ["y"]}
    _, issues = load_analysis_plan({"modules": [base]}, known_raw_keys={"x", "y"})
    assert any(i.code == "analysis_output_collision" for i in issues)
    consumer = dict(base, name="two", inputs=["y"], outputs=["z"])
    # The fixture declaration mismatch is also correctly rejected, while graph reports the disabled source.
    _, issues = load_analysis_plan({"modules": [dict(base, enabled=False), consumer]})
    assert any(i.code in {"analysis_dependency_disabled", "analysis_contract_invalid"} for i in issues)
