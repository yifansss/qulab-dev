"""Post-run recompute API and ``python -m`` command line interface."""

from __future__ import annotations

import argparse
import json
import re
import sys
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from qulab import __version__
from qulab.core import DerivedData
from qulab.storage import RunReader

from .config import load_analysis_plan
from .engine import _normalize_result
from .lineage import input_lineage, source_run_fingerprint, stable_hash
from .models import ComputeModulePlan, ComputePoint, json_safe
from .registry import AnalysisModuleRegistry, DEFAULT_ANALYSIS_REGISTRY
from .result_store import AnalysisResultStore, cleanup_stale_temps


@dataclass(frozen=True)
class RecomputeResult:
    result_id: str
    result_path: Path | None
    selected_modules: tuple[str, ...]
    point_count: int
    output_keys: tuple[str, ...]
    dry_run: bool = False
    reused: bool = False


def recompute_run(run_path: Path | str, modules: Iterable[str], *, config: Path | str | Mapping[str, Any] | None = None,
                  result_id: str | None = None, overrides: Mapping[str, Any] | None = None,
                  backend: str = "csv", dry_run: bool = False, allow_partial: bool = False,
                  force_run_post: bool = False, reuse_if_identical: bool = False,
                  registry: AnalysisModuleRegistry | None = None) -> RecomputeResult:
    source = Path(run_path)
    if not source.is_dir(): raise FileNotFoundError(f"run folder not found: {source}")
    reader = RunReader(source)
    status = reader.metadata.get("status")
    if status not in {"completed", None} and not allow_partial:
        raise ValueError(f"source run status is {status!r}; pass allow_partial=True to include completed points")
    raw_config = _load_config(config if config is not None else source / "config.yaml")
    analysis_config = deepcopy(raw_config.get("analysis", raw_config))
    selected_names = tuple(dict.fromkeys(modules))
    if not selected_names: raise ValueError("at least one --module is required")
    _apply_overrides(analysis_config, selected_names, overrides or {})
    plan, issues = load_analysis_plan(analysis_config, known_raw_keys=reader.list_data_keys(group="raw"))
    errors = [issue for issue in issues if issue.severity == "error"]
    if plan is None or errors: raise ValueError("; ".join(f"[{i.code}] {i.message}" for i in errors) or "analysis plan unavailable")
    selected = _dependency_closure(plan.modules, selected_names)
    if not force_run_post:
        ineligible = [module.instance_name for module in selected if not module.run_post]
        if ineligible: raise ValueError(f"modules are not eligible for post-run execution: {', '.join(ineligible)}")
    raw_inputs = tuple(dict.fromkeys(key for module in selected for key in module.inputs
                                    if not any(key in upstream.effective_outputs for upstream in selected)))
    include_status = ("ok", "partial") if allow_partial else ("ok",)
    points = list(reader.iter_compute_points(raw_inputs, include_status=include_status))
    output_keys = tuple(key for module in selected for key in module.effective_outputs)
    fingerprint = source_run_fingerprint(source)
    config_hash = stable_hash({"analysis": analysis_config, "modules": selected_names, "overrides": overrides or {}})
    result_id = result_id or f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{'_'.join(selected_names)}_{config_hash[:10]}"
    if dry_run:
        return RecomputeResult(result_id, None, tuple(m.instance_name for m in selected), len(points), output_keys, True)
    if reuse_if_identical:
        reused = _find_identical(source, config_hash, fingerprint["fingerprint"])
        if reused:
            return RecomputeResult(reused.name, reused, tuple(m.instance_name for m in selected), len(points), output_keys, reused=True)
    backends = ["csv", "zarr"] if backend == "both" else [backend]
    metadata = {"qulab_version": __version__, "config_hash": config_hash, "source_fingerprint": fingerprint,
                "modules": [module.to_dict() for module in selected], "dependency_edges": list(plan.dependency_edges),
                "input_lineage": input_lineage(raw_inputs), "output_keys": list(output_keys), "backend": backends,
                "selected_modules": list(selected_names), "overrides": json_safe(overrides or {})}
    store = AnalysisResultStore(source, result_id, backends=backends, analysis_config={"analysis": analysis_config}, metadata=metadata)
    runtimes: dict[str, Any] = {}; setup_order: list[str] = []
    module_registry = registry or DEFAULT_ANALYSIS_REGISTRY
    try:
        store.open()
        for module in selected:
            runtime = module_registry.instantiate(module)
            runtime.setup(deepcopy(dict(module.args)), {"mode": "post", "source_run": str(source), "result_id": result_id})
            runtimes[module.instance_name] = runtime; setup_order.append(module.instance_name)
        for point in points:
            values = deepcopy(dict(point.data)); emitted = 0
            for module in selected:
                missing = [key for key in module.inputs if key not in values]
                if missing:
                    if module.fail_policy == "fail": raise ValueError(f"{module.instance_name} missing inputs {missing} at {point.point_id}")
                    store.metadata["skipped_point_count"] += 1
                    continue
                compute_point = ComputePoint(point.point_id, deepcopy(point.coords),
                    {key: deepcopy(values[key]) for key in module.inputs}, deepcopy(point.metadata), point.timestamp)
                try:
                    normalized = _normalize_result(runtimes[module.instance_name].process_point(compute_point))
                    if normalized is None or not normalized.data: continue
                    data, units = _map_result(module, normalized.data, normalized.units)
                    collision = set(data) & set(values)
                    if collision: raise ValueError(f"output collision: {sorted(collision)}")
                    values.update(deepcopy(data))
                    store.append(DerivedData(point_id=point.point_id, coords=deepcopy(point.coords), data=data,
                        source_module=module.instance_name, module_version=module.source_identity.version,
                        input_keys=list(module.inputs), output_keys=list(data), units=units,
                        metadata=json_safe(normalized.metadata), quality=json_safe(normalized.quality),
                        save=True, show=False, run_mode="post"))
                    emitted += 1
                except Exception:
                    if module.fail_policy == "fail": raise
                    store.metadata["error_count"] += 1
            if emitted == 0: store.metadata["skipped_point_count"] += 1
        path = store.commit()
        return RecomputeResult(result_id, path, tuple(m.instance_name for m in selected), len(points), output_keys)
    except BaseException as exc:
        store.fail(exc); raise
    finally:
        for name in reversed(setup_order):
            try: runtimes[name].close()
            except Exception: pass


def _map_result(module: ComputeModulePlan, data: Mapping[str, Any], units: Mapping[str, Any]):
    returned = set(data); declared = set(module.declared_outputs); effective = set(module.effective_outputs)
    if returned <= declared:
        mapped = {out: data[src] for src, out in zip(module.declared_outputs, module.effective_outputs) if src in data}
        mapped_units = {out: units[src] for src, out in zip(module.declared_outputs, module.effective_outputs) if src in units}
    elif returned <= effective:
        mapped = dict(data); mapped_units = dict(units)
    else: raise ValueError(f"{module.instance_name} returned undeclared outputs: {sorted(returned - declared - effective)}")
    return json_safe(mapped), json_safe(mapped_units)


def _dependency_closure(plans: tuple[ComputeModulePlan, ...], names: tuple[str, ...]) -> tuple[ComputeModulePlan, ...]:
    by_name = {module.instance_name: module for module in plans}
    missing = [name for name in names if name not in by_name]
    if missing: raise KeyError(f"unknown analysis module(s): {', '.join(missing)}")
    needed = set(names); changed = True
    while changed:
        changed = False
        for name in tuple(needed):
            for dep in by_name[name].dependencies:
                if dep not in needed: needed.add(dep); changed = True
    return tuple(module for module in plans if module.instance_name in needed and module.enabled)


def _load_config(source: Path | str | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(source, Mapping): return deepcopy(dict(source))
    path = Path(source)
    if not path.exists(): raise FileNotFoundError(f"analysis config not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict): raise ValueError("analysis config must be a mapping")
    return raw


def _apply_overrides(analysis: dict[str, Any], selected: tuple[str, ...], overrides: Mapping[str, Any]) -> None:
    modules = analysis.get("modules", [])
    by_name = {item.get("name"): item for item in modules if isinstance(item, dict)}
    for key, value in overrides.items():
        if "." in key and key.split(".", 1)[0] in by_name:
            module_name, arg = key.split(".", 1)
        elif len(selected) == 1:
            module_name, arg = selected[0], key
        else: raise ValueError(f"override {key!r} must be qualified as module.argument")
        if module_name not in by_name: raise KeyError(f"unknown override module: {module_name}")
        by_name[module_name].setdefault("args", {})[arg] = json_safe(value)


def _find_identical(source: Path, config_hash: str, fingerprint: str) -> Path | None:
    root = source / "analysis"
    if not root.exists(): return None
    for path in sorted(root.iterdir()):
        metadata = path / "metadata.json"
        if path.is_dir() and metadata.exists():
            data = json.loads(metadata.read_text())
            if data.get("status") == "completed" and data.get("config_hash") == config_hash and data.get("source_fingerprint", {}).get("fingerprint") == fingerprint:
                return path
    return None


def _parse_set(items: list[str]) -> dict[str, Any]:
    output = {}
    for item in items:
        if "=" not in item: raise ValueError(f"--set requires key=value: {item}")
        key, raw = item.split("=", 1)
        output[key] = _normalize_yaml_numbers(yaml.safe_load(raw))
    return output


def _normalize_yaml_numbers(value: Any) -> Any:
    if isinstance(value, str) and re.fullmatch(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)[eE][-+]?\d+", value):
        return float(value)
    if isinstance(value, list): return [_normalize_yaml_numbers(item) for item in value]
    if isinstance(value, dict): return {key: _normalize_yaml_numbers(item) for key, item in value.items()}
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Recompute immutable post-run analysis results")
    parser.add_argument("--run", required=True); parser.add_argument("--module", action="append", required=True)
    parser.add_argument("--config"); parser.add_argument("--result-id"); parser.add_argument("--set", action="append", default=[])
    parser.add_argument("--backend", choices=("csv", "zarr", "both"), default="csv"); parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-partial", action="store_true"); parser.add_argument("--force-run-post", action="store_true")
    parser.add_argument("--reuse-if-identical", action="store_true"); parser.add_argument("--cleanup-temp", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.cleanup_temp: cleanup_stale_temps(args.run)
        result = recompute_run(args.run, args.module, config=args.config, result_id=args.result_id,
            overrides=_parse_set(args.set), backend=args.backend, dry_run=args.dry_run,
            allow_partial=args.allow_partial, force_run_post=args.force_run_post, reuse_if_identical=args.reuse_if_identical)
        print(json.dumps({"result_id": result.result_id, "result_path": str(result.result_path) if result.result_path else None,
                          "modules": result.selected_modules, "point_count": result.point_count,
                          "output_keys": result.output_keys, "dry_run": result.dry_run, "reused": result.reused}))
        return 0
    except (ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr); return 2
    except (FileNotFoundError, OSError) as exc:
        print(str(exc), file=sys.stderr); return 3
    except Exception as exc:
        print(str(exc), file=sys.stderr); return 4


if __name__ == "__main__":
    raise SystemExit(main())
