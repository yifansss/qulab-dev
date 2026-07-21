"""Conservative legacy ASG template and bundle migration assistance."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from qulab.sequence_bundles import load_sequence_bundle
from .providers.asg_model import inspect_template


def sequence_plan_from_template(template: str | Path, *, resource: str = "asg", plan_id: str = "imported_sequence",
                                project_root: str | Path | None = None) -> dict[str, Any]:
    source = Path(template).resolve()
    inspection = inspect_template(source)
    display_path: str
    if project_root is not None:
        try: display_path = str(source.relative_to(Path(project_root).resolve()))
        except ValueError: display_path = str(source)
    else: display_path = str(source)
    summary = [{"channel": item["name"], "pulse_count": len(item["pulses"]), "pbn": item["pbn"]}
               for item in inspection.channels]
    return {
        "schema_version": 1, "name": f"imported_{plan_id}",
        "description": "Imported generic ASG template. Target aliases and physical roles are intentionally unbound.",
        "migration": {"source_template_sha256": inspection.template_sha256, "inspection": summary,
                      "warnings": ["Assign pulse targets and physical channel roles before adding transforms or hardware output."]},
        "resources": {resource: {"adapter": "mock_asg", "capabilities": ["pulse_sequencer"]}},
        "sequence_plans": {plan_id: {
            "resource": resource, "family": {"provider": "qulab.sequence_generation.providers.asg_template", "version": "1"},
            "template": display_path, "targets": {}, "parameters": {"point_index": {"mode": "explicit", "values": [0]}},
            "sampling": {"mode": "cartesian", "order": ["point_index"]}, "materialize": {"cache": True, "max_points": 1},
        }},
        "procedure": [{"sequence_sweep": {"plan": plan_id, "body": [{"measurement": {"name": "imported_point", "body": []}}]}}],
        "cleanup": [{"call": f"{resource}.stop"}],
    }


def write_sequence_plan_from_template(template: str | Path, output: str | Path, *, resource: str = "asg",
                                      plan_id: str = "imported_sequence", project_root: str | Path | None = None,
                                      force: bool = False) -> Path:
    destination = Path(output)
    if destination.exists() and not force: raise FileExistsError(f"Output already exists: {destination}; pass force=True to replace it")
    config = sequence_plan_from_template(template, resource=resource, plan_id=plan_id, project_root=project_root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return destination


def inspect_bundle_for_migration(manifest: str | Path) -> dict[str, Any]:
    bundle = load_sequence_bundle(manifest)
    return {"bundle_id": bundle.id, "resource": bundle.resource, "coordinates": list(bundle.entries[0].coordinates),
            "entry_count": len(bundle.entries), "generator": deepcopy(bundle.generator),
            "reversible": False, "warning": "Concrete bundle entries do not preserve target transforms; import a source template and bind targets explicitly."}
