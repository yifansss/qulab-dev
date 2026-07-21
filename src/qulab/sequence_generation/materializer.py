"""Framework-owned immutable sequence bundle materialization."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

import yaml

from qulab.sequence_bundles import load_sequence_bundle, validate_bundle_coverage

from .errors import SequenceGenerationError
from .models import MaterializedSequenceBundle, SequenceGeneratorProvider, SequenceSweepPlan, SourceIdentity, json_safe
from .sampling import enumerate_plan_points, normalize_parameter_values


GENERATION_SCHEMA_VERSION = 1


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(json_safe(value), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def materialize_sequence_plan(
    plan: SequenceSweepPlan,
    provider: SequenceGeneratorProvider,
    *,
    cache_root: Path,
    source_identity: SourceIdentity,
) -> MaterializedSequenceBundle:
    spec = provider.describe()
    if callable(getattr(provider, "configure_plan", None)):
        provider.configure_plan(plan)
    validation = provider.validate_plan(plan)
    if not validation.ok:
        issue = next(item for item in validation.issues if item.severity == "error")
        raise SequenceGenerationError(issue.code, issue.message, context=issue.context)
    values = normalize_parameter_values(plan, spec)
    points = enumerate_plan_points(plan, values)
    if not points:
        raise SequenceGenerationError("sequence_sweep_empty", f"Sequence plan '{plan.id}' produced no points")
    if not plan.sampling_order:
        raise SequenceGenerationError("sequence_sweep_empty", f"Sequence plan '{plan.id}' must sweep at least one parameter")
    if len(points) > plan.materialize.max_points:
        raise SequenceGenerationError(
            "sequence_sweep_too_large", f"Sequence plan '{plan.id}' has {len(points)} points; maximum is {plan.materialize.max_points}",
            context={"point_count": len(points), "max_points": plan.materialize.max_points},
        )
    template_hash = _hash_bytes(plan.template.read_bytes()) if plan.template is not None else None
    hash_input = {
        "generation_schema": GENERATION_SCHEMA_VERSION, "plan": plan.to_dict(), "values": values,
        "provider": source_identity.to_dict(), "family": spec.to_dict(), "template_sha256": template_hash,
    }
    plan_hash = _hash_bytes(_canonical(hash_input))
    parent = Path(cache_root) / plan.id
    target = parent / plan_hash
    if not plan.materialize.cache:
        target = parent / f"{plan_hash}-{next(tempfile._get_candidate_names())}"
    bundle_id = f"generated_{plan.id}"

    def validated(path: Path, cache_hit: bool) -> MaterializedSequenceBundle:
        manifest = path / "manifest.yaml"
        bundle = load_sequence_bundle(manifest, declared_id=bundle_id, declared_resource=plan.resource)
        coverage = validate_bundle_coverage(bundle, (point.coordinates for point in points))
        if not coverage.ok or len(bundle.entries) != len(points):
            raise SequenceGenerationError("generated_bundle_coverage_failed", f"Generated bundle '{bundle_id}' does not cover its plan")
        return MaterializedSequenceBundle(plan, spec, bundle_id, manifest, bundle.manifest_sha256, plan_hash,
                                          len(points), cache_hit, values, source_identity, template_hash)

    if target.exists():
        try:
            return validated(target, True)
        except Exception as exc:
            raise SequenceGenerationError("sequence_cache_invalid", f"Cached sequence bundle is invalid: {target}: {exc}") from exc
    parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{plan_hash}.tmp-", dir=parent))
    try:
        sequences = temporary / "sequences"
        sequences.mkdir()
        entries = []
        for point in points:
            try:
                generated = provider.generate_point(point.parameters, template=plan.template)
            except Exception as exc:
                raise SequenceGenerationError("sequence_generation_failed", f"Provider failed at point {point.index}: {exc}") from exc
            if not isinstance(generated.sequence_bytes, bytes) or not generated.sequence_bytes:
                raise SequenceGenerationError("sequence_output_invalid", "Provider must return non-empty bytes")
            extension = generated.extension
            if not isinstance(extension, str) or not re.fullmatch(r"\.[A-Za-z0-9]{1,12}", extension):
                raise SequenceGenerationError("sequence_output_invalid", f"Unsafe generated extension: {extension!r}")
            try:
                metadata = json_safe(generated.metadata)
                _canonical(metadata)
            except Exception as exc:
                raise SequenceGenerationError("sequence_output_invalid", f"Generated metadata is not JSON-safe: {exc}") from exc
            entry_id = f"point_{point.index:06d}"
            filename = f"{entry_id}{extension.lower()}"
            data_path = sequences / filename
            data_path.write_bytes(generated.sequence_bytes)
            entries.append({"id": entry_id, "coordinates": dict(point.coordinates),
                            "sequence_file": f"sequences/{filename}", "sha256": _hash_bytes(generated.sequence_bytes),
                            "metadata": metadata})
        coordinate_specs = {}
        family_parameters = {item.name: item for item in spec.parameters}
        for name in plan.sampling_order:
            exported = plan.parameters[name].expose_as or name
            coordinate_specs[exported] = {"values": list(values[name])}
            unit = family_parameters[name].unit if name in family_parameters else plan.parameters[name].unit
            if unit:
                coordinate_specs[exported]["unit"] = unit
        manifest = {
            "schema_version": 1, "kind": "sequence_bundle", "id": bundle_id, "resource": plan.resource,
            "format": spec.output_format, "coordinates": coordinate_specs, "entries": entries,
            "generator": {"provider": source_identity.provider, "version": source_identity.version,
                          "source_sha256": source_identity.source_sha256, "plan_hash": plan_hash,
                          "template_sha256": template_hash, "generation_schema": GENERATION_SCHEMA_VERSION},
        }
        (temporary / "manifest.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
        validated(temporary, False)
        os.replace(temporary, target)
        return validated(target, False)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
