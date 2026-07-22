"""Explicit, provenance-aware loading for user compute modules."""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import inspect
import re
import sys
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from types import ModuleType
from typing import Any

from qulab.paths import project_root, resolve_project_path

from .base import FunctionComputeAdapter
from .errors import AnalysisError
from .models import AnalysisSourceIdentity, ComputeArgumentSpec, ComputeModulePlan, ComputeModuleSpec


class AnalysisModuleRegistry:
    def __init__(self) -> None:
        self._objects: dict[str, Any] = {}

    def register(self, target: str, obj: Any) -> None:
        if not target:
            raise AnalysisError("analysis_module_target_invalid", "Registry target cannot be empty")
        self._objects[target] = obj

    def describe(self, plan: ComputeModulePlan) -> ComputeModuleSpec:
        obj, module = self._load_object(plan)
        if plan.object_kind == "class":
            for attr in ("setup", "process_point", "close"):
                if not callable(getattr(obj, attr, None)):
                    raise AnalysisError("analysis_contract_invalid", f"Class '{plan.object_name}' lacks callable {attr}()")
        elif not callable(obj):
            raise AnalysisError("analysis_contract_invalid", f"Function '{plan.object_name}' is not callable")
        version = str(getattr(obj, "version", getattr(module, "__version__", "0")))
        inputs = _string_tuple(getattr(obj, "input_keys", plan.inputs), "input_keys")
        outputs = _string_tuple(getattr(obj, "output_keys", plan.declared_outputs), "output_keys")
        if inputs != plan.inputs or outputs != plan.declared_outputs:
            raise AnalysisError(
                "analysis_contract_invalid",
                f"Module '{plan.instance_name}' declarations do not match YAML inputs/outputs",
            )
        argument_specs = _argument_specs(obj)
        return ComputeModuleSpec(str(getattr(obj, "name", plan.instance_name)), version, inputs, outputs, argument_specs)

    def instantiate(self, plan: ComputeModulePlan) -> Any:
        obj, _ = self._load_object(plan)
        if plan.object_kind == "function":
            if not callable(obj):
                raise AnalysisError("analysis_contract_invalid", f"'{plan.object_name}' is not callable")
            return FunctionComputeAdapter(obj, name=plan.instance_name, version=plan.source_identity.version,
                                          input_keys=plan.inputs, output_keys=plan.declared_outputs)
        try:
            instance = obj()
        except Exception as exc:
            raise AnalysisError("analysis_contract_invalid", f"Could not instantiate '{plan.object_name}': {exc}") from exc
        for attr in ("setup", "process_point", "close"):
            if not callable(getattr(instance, attr, None)):
                raise AnalysisError("analysis_contract_invalid", f"Class '{plan.object_name}' lacks callable {attr}()")
        return instance

    def resolve(self, import_target: str, object_name: str, object_kind: str,
                *, project_base: str | Path | None = None) -> tuple[Any, ModuleType, AnalysisSourceIdentity]:
        key = f"{import_target}:{object_name}"
        if key in self._objects:
            obj = self._objects[key]
            module = inspect.getmodule(obj)
            version = str(getattr(obj, "version", getattr(module, "__version__", "0")))
            return obj, module or ModuleType("registered"), AnalysisSourceIdentity(import_target, None, None, version)
        module, path, digest = _load_module(import_target, project_base)
        if not hasattr(module, object_name):
            raise AnalysisError("analysis_object_not_found", f"Object '{object_name}' was not found in '{import_target}'")
        obj = getattr(module, object_name)
        if object_kind == "class" and not inspect.isclass(obj):
            raise AnalysisError("analysis_contract_invalid", f"'{object_name}' must be a class")
        if object_kind == "function" and not callable(obj):
            raise AnalysisError("analysis_contract_invalid", f"'{object_name}' must be callable")
        version = str(getattr(obj, "version", getattr(module, "__version__", "0")))
        return obj, module, AnalysisSourceIdentity(import_target, str(path) if path else None, digest, version)

    def _load_object(self, plan: ComputeModulePlan) -> tuple[Any, ModuleType]:
        target = plan.source_identity.resolved_path if plan.import_target.endswith(".py") and plan.source_identity.resolved_path else plan.import_target
        obj, module, identity = self.resolve(target, plan.object_name, plan.object_kind)
        if identity.sha256 and plan.source_identity.sha256 and identity.sha256 != plan.source_identity.sha256:
            raise AnalysisError("analysis_version_mismatch", f"Source changed after plan creation for '{plan.instance_name}'")
        return obj, module


def _load_module(target: str, project_base: str | Path | None) -> tuple[ModuleType, Path | None, str | None]:
    if not isinstance(target, str) or not target.strip():
        raise AnalysisError("analysis_module_target_invalid", "Analysis module target must be a non-empty string")
    looks_like_file = target.endswith(".py") or "/" in target or "\\" in target
    if looks_like_file:
        path = resolve_project_path(target, base_dir=project_base or project_root(), must_exist=True)
        if path is None or not path.is_file():
            raise AnalysisError("analysis_module_not_found", f"Analysis module file not found: {target}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        synthetic = f"_qulab_analysis_{re.sub(r'[^A-Za-z0-9_]', '_', path.stem)}_{digest[:16]}"
        existing = sys.modules.get(synthetic)
        if existing is not None:
            return existing, path, digest
        spec = importlib.util.spec_from_file_location(synthetic, path)
        if spec is None or spec.loader is None:
            raise AnalysisError("analysis_module_import_failed", f"Could not create import spec for: {target}")
        module = importlib.util.module_from_spec(spec)
        try:
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                spec.loader.exec_module(module)
        except Exception as exc:
            raise AnalysisError("analysis_module_import_failed", f"Could not import analysis module '{target}': {exc}") from exc
        sys.modules[synthetic] = module
        return module, path, digest
    try:
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            module = importlib.import_module(target)
    except ModuleNotFoundError as exc:
        code = "analysis_module_not_found" if exc.name == target or target.startswith(f"{exc.name}.") else "analysis_module_import_failed"
        raise AnalysisError(code, f"Could not import analysis module '{target}': {exc}") from exc
    except Exception as exc:
        raise AnalysisError("analysis_module_import_failed", f"Could not import analysis module '{target}': {exc}") from exc
    source = inspect.getsourcefile(module)
    path = Path(source).resolve() if source else None
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest() if path else None
    except OSError:
        digest = None
    return module, path, digest


def _string_tuple(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value or any(not isinstance(item, str) or not item for item in value):
        raise AnalysisError("analysis_contract_invalid", f"{label} must be a non-empty string sequence")
    return tuple(value)


def _argument_specs(obj: Any) -> tuple[ComputeArgumentSpec, ...]:
    describe = getattr(obj, "describe_arguments", None)
    if not callable(describe):
        return ()
    raw = describe()
    if not isinstance(raw, (list, tuple)) or any(not isinstance(item, ComputeArgumentSpec) for item in raw):
        raise AnalysisError("analysis_contract_invalid", "describe_arguments() must return ComputeArgumentSpec values")
    return tuple(raw)


DEFAULT_ANALYSIS_REGISTRY = AnalysisModuleRegistry()
