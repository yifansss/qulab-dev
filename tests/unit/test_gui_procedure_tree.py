from __future__ import annotations

from pathlib import Path

from qulab.config import load_experiment_config
from qulab.gui.procedure_tree import build_procedure_tree


ROOT = Path(__file__).resolve().parents[2]


def test_build_procedure_tree_contains_required_step_kinds() -> None:
    config = load_experiment_config(ROOT / "configs" / "experiments" / "dry_run_rabi.yaml")

    roots = build_procedure_tree(config)
    kinds: list[str] = []
    labels: list[str] = []

    def walk(node) -> None:
        kinds.append(node.kind)
        labels.append(node.label)
        for child in node.children:
            walk(child)

    for root in roots:
        walk(root)

    assert [root.kind for root in roots] == ["setup", "procedure", "cleanup"]
    assert "scan" in kinds
    assert "measurement" in kinds
    assert "average" in kinds
    assert "run" in kinds
    assert "call" in kinds
    assert any(label == "scan tau_s" for label in labels)
    assert any(label == "run readout" for label in labels)
