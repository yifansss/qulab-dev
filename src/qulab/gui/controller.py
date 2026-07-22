"""Headless-friendly backend for the Tk operator console."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from threading import RLock
from typing import Any, Callable

from qulab.config import ConfigLoadResult, ParsedExperiment, parse_experiment_config, validate_config_candidate
from qulab.config.errors import ConfigValidationError
from qulab.config.refs import parameter_refs_to_strings
from qulab.core import Event, EventBus, ExperimentExecutor
from qulab.analysis import create_live_compute_engine
from qulab.analysis.validation import collect_known_raw_keys
from qulab.sequence_files import discover_sequence_references, inspect_sequence_file
from qulab.sequence_generation import SequenceGenerationError, prepare_and_parse_experiment_config
from qulab.sequence_generation.preparation import parse_sequence_plans
from qulab.sequence_generation.registry import DEFAULT_PROVIDER_REGISTRY
from qulab.sequence_generation.sampling import normalize_parameter_values
from qulab.sequence_generation.providers.asg_model import build_target_selector, inspect_template
from qulab.storage import DatasetModel, HistoricalRunWorkspace, RunReader, RunStore, SliceController
from qulab.storage.run_reader import BackendPreference
from qulab.storage.slicing import HeatmapData, LineData, TraceData
from .workflow_model import (
    Path as WorkflowPath,
    add_step,
    build_workflow_tree,
    delete_step,
    duplicate_step,
    update_node,
)
from .yaml_editor import save_config_yaml

from .models import (
    ParameterEdit,
    PreflightIssueViewModel,
    PreflightViewModel,
    ResourceViewModel,
    RunViewModel,
    SequenceSnapshotViewModel,
    extract_parameter_edits,
    parse_parameter_value,
    update_config_value,
)
from .operator_parameters import OperatorParameterSpec, apply_operator_parameter, discover_operator_parameters
from .sequence_sweep_model import PlanEstimate, SequencePlanViewModel, SequenceSweepEditorModel
from .live_data_catalog import LiveDataCatalog, LivePointBuffer
from .live_plot_model import LivePlotModel, LivePlotSelection
from .analysis_status_model import AnalysisStatusModel
from .sequence_context_model import SequenceContextModel
from .workflow_composer import WorkflowComposerModel
from .sequence_authoring import SequenceAuthoringModel
from .sequence_authoring_presenter import GuidedSequenceViewState, SequenceAuthoringPresenter


class OperatorController:
    """Load, edit, preflight, and execute mock/dry-run experiment configs."""

    def __init__(self, run_root: Path | str = "runs") -> None:
        self.run_root = Path(run_root)
        self.config_path: Path | None = None
        self.config: dict[str, Any] | None = None
        self.parsed: ParsedExperiment | None = None
        self.last_run_path: Path | None = None
        self.sequence_sweep_model: SequenceSweepEditorModel | None = None
        self.last_candidate_result: ConfigLoadResult | None = None
        self.historical_workspace: HistoricalRunWorkspace | None = None
        self.historical_replay: Any | None = None
        self.historical_live_catalog = LiveDataCatalog()
        self.historical_live_buffer = LivePointBuffer()
        self.historical_analysis_status = AnalysisStatusModel()
        self.historical_sequence_context = SequenceContextModel()
        self._workflow_composer: WorkflowComposerModel | None = None
        self._sequence_authoring: SequenceAuthoringModel | None = None
        self._sequence_prepared_revisions: dict[str, str] = {}
        self._live_lock = RLock()
        self.live_catalog = LiveDataCatalog()
        self.live_buffer = LivePointBuffer()
        self.live_plot_model = LivePlotModel(self.live_catalog, self.live_buffer)
        self.analysis_status_model = AnalysisStatusModel()
        self.sequence_context_model = SequenceContextModel()
        self._live_selected_keys: tuple[str, ...] | None = None
        self._live_selection_options: dict[str, Any] = {"plot_type": "auto"}

    @property
    def current_config(self) -> dict[str, Any]:
        self._require_config()
        assert self.config is not None
        return deepcopy(self.config)

    def load_config(self, path: Path | str) -> ConfigLoadResult:
        """Validate and atomically activate a candidate without hardware I/O."""

        result = validate_config_candidate(path)
        if result.ok and result.candidate_config is not None and result.parsed is not None:
            self.config_path = Path(path)
            self.config = deepcopy(result.candidate_config)
            self.parsed = result.parsed
            self.sequence_sweep_model = SequenceSweepEditorModel.load(self.config)
            self._workflow_composer = WorkflowComposerModel(self.config)
            self._sequence_authoring = SequenceAuthoringModel(self.config, self.sequence_sweep_model)
            self._sequence_prepared_revisions = {}
            self.reset_live_state()
            result = replace(result, activated=True)
        self.last_candidate_result = result
        return result

    @property
    def has_active_config(self) -> bool:
        return self.config is not None

    def candidate_issues(self) -> tuple[PreflightIssueViewModel, ...]:
        if self.last_candidate_result is None:
            return ()
        return tuple(
            PreflightIssueViewModel(
                item.severity,
                item.code,
                item.message,
                item.location,
                item.hint or item.excerpt or "",
                item.workflow_path,
            )
            for item in self.last_candidate_result.diagnostics
        )

    def save_config(self, path: Path | str) -> Path:
        self._require_config()
        assert self.config is not None
        save_path = save_config_yaml(self.config, path)
        self.config_path = save_path
        return save_path

    def get_parameter_edit_model(self) -> list[ParameterEdit]:
        self._require_config()
        assert self.config is not None
        return extract_parameter_edits(self.config)

    def update_parameter(self, path_or_id: str, value: Any) -> None:
        self._require_config()
        assert self.config is not None
        edits = self.get_parameter_edit_model()
        edit_by_id = {edit.id: edit for edit in edits}
        edit = edit_by_id.get(path_or_id)
        if edit is None:
            raise KeyError(f"Unknown editable parameter: {path_or_id}")
        parsed_value = parse_parameter_value(value, edit.value_type) if isinstance(value, str) else value
        update_config_value(self.config, edit.path, parsed_value)
        self.parsed = None

    def get_operator_parameters(self) -> list[OperatorParameterSpec]:
        self._require_config()
        assert self.config is not None
        return discover_operator_parameters(self.workflow_tree(), self.config)

    def apply_operator_parameter(self, spec_name: str, value: Any) -> None:
        self._require_config()
        assert self.config is not None
        specs = {item.name: item for item in self.get_operator_parameters()}
        selected = specs.get(spec_name)
        apply_operator_parameter(self.workflow_tree(), self.config, spec_name, value)
        if selected is not None and selected.source.startswith("sequence_plans."):
            parts = selected.source.split(".")
            if len(parts) > 1:
                self._sequence_model()._edited(parts[1])
        self.parsed = None

    def prepare(self) -> PreflightViewModel:
        self._require_config()
        assert self.config is not None
        try:
            self.parsed = prepare_and_parse_experiment_config(deepcopy(self.config))
        except SequenceGenerationError as exc:
            raise ConfigValidationError(f"[{exc.code}] {exc}") from exc
        if self.sequence_sweep_model is not None and self.parsed.sequence_preparation is not None:
            for plan_id, bundle in self.parsed.sequence_preparation.materialized.items():
                self.sequence_sweep_model.mark_prepared(plan_id, bundle.plan_hash)
                self._sequence_prepared_revisions[plan_id] = self.sequence_authoring().revision(plan_id)
        return self._preflight_view(self.parsed)

    def prepare_sequence_plan(self, plan_id: str, *, expected_revision: str | None = None) -> PreflightViewModel:
        """Prepare one authoring revision and discard a raced/stale result."""
        self._require_config(); assert self.config is not None
        revision = expected_revision or self.sequence_authoring().revision(plan_id)
        try: candidate = prepare_and_parse_experiment_config(deepcopy(self.config))
        except SequenceGenerationError as exc: raise ConfigValidationError(f"[{exc.code}] {exc}") from exc
        if self.sequence_authoring().revision(plan_id) != revision:
            raise ConfigValidationError("[sequence_prepare_revision_changed] Plan changed while Prepare was running; result discarded")
        self.parsed = candidate
        if candidate.sequence_preparation is not None:
            for prepared_id, bundle in candidate.sequence_preparation.materialized.items():
                self._sequence_model().mark_prepared(prepared_id, bundle.plan_hash)
                self._sequence_prepared_revisions[prepared_id] = self.sequence_authoring().revision(prepared_id)
        return self._preflight_view(candidate)

    def list_sequence_plans(self) -> list[SequencePlanViewModel]:
        return self._sequence_model().list_plans()

    def list_sequence_providers(self) -> tuple[dict[str, Any], ...]:
        return DEFAULT_PROVIDER_REGISTRY.descriptors()

    def create_sequence_plan(self, plan_id: str, resource: str, provider: str, template: str | None = None) -> None:
        self._sequence_model().create_plan(plan_id, resource, provider, template); self.parsed = None

    def create_guided_sequence_plan(self, plan_id: str, resource: str, mode: str, *,
                                    provider: str | None = None, template: str | None = None) -> GuidedSequenceViewState:
        selected_provider = provider if mode == "curated" else "asg_template"
        if not selected_provider: raise ValueError("Curated mode requires a provider")
        if mode in {"generic", "standalone"} and not template: raise ValueError(f"{mode} mode requires a template")
        self.create_sequence_plan(plan_id, resource, selected_provider, template)
        if mode == "standalone": self.config["sequence_plans"][plan_id].setdefault("options", {})["authoring_mode"] = "standalone"
        self._sequence_edited(plan_id)
        return self.get_guided_sequence_state(plan_id)

    def duplicate_sequence_plan(self, plan_id: str, new_plan_id: str) -> None:
        self._sequence_model().duplicate_plan(plan_id, new_plan_id); self.parsed = None

    def delete_sequence_plan(self, plan_id: str) -> None:
        self._sequence_model().remove_plan(plan_id); self.parsed = None

    def update_sequence_plan_parameter(self, plan_id: str, name: str, patch: dict[str, Any]) -> None:
        self.sequence_authoring().update_parameter(plan_id, name, patch); self._sequence_edited(plan_id)

    def update_sequence_plan_target(self, plan_id: str, alias: str, patch: dict[str, Any]) -> None:
        self._sequence_model().update_target(plan_id, alias, patch); self._sequence_edited(plan_id)

    def select_sequence_plan_target(self, plan_id: str, alias: str, channel: str, pulse: int) -> None:
        plan = parse_sequence_plans(self.current_config)[plan_id]
        if plan.template is None: raise ValueError(f"Sequence plan '{plan_id}' has no template")
        selector = build_target_selector(plan.template, channel, pulse, alias=alias)
        selector.pop("alias", None); self.update_sequence_plan_target(plan_id, alias, selector)

    def update_sequence_plan_constraints(self, plan_id: str, constraints: list[dict[str, Any]]) -> None:
        self._sequence_model().update_constraints(plan_id, constraints); self._sequence_edited(plan_id)

    def set_sequence_plan_sampling_order(self, plan_id: str, order: list[str]) -> None:
        self._sequence_model().set_sampling_order(plan_id, order); self._sequence_edited(plan_id)

    def estimate_sequence_plan(self, plan_id: str) -> PlanEstimate:
        return self._sequence_model().estimate(plan_id)

    def inspect_sequence_template(self, plan_id: str):
        plan = parse_sequence_plans(self.current_config)[plan_id]
        if plan.template is None: raise ValueError(f"Sequence plan '{plan_id}' has no template")
        return inspect_template(plan.template)

    def preview_sequence_plan(self, plan_id: str, coordinates: dict[str, Any] | None = None):
        plan = parse_sequence_plans(self.current_config)[plan_id]
        provider, _ = DEFAULT_PROVIDER_REGISTRY.load(plan.provider, plan.provider_version)
        if callable(getattr(provider, "configure_plan", None)): provider.configure_plan(plan)
        values = normalize_parameter_values(plan, provider.describe())
        parameters = {name: items[0] for name, items in values.items()}
        for name, value in (coordinates or {}).items():
            internal = next((key for key, raw in plan.parameters.items() if (raw.expose_as or key) == name), name)
            if internal not in parameters: raise KeyError(name)
            parameters[internal] = value
        return provider.preview_point(parameters, template=plan.template)

    def compiled_sequence_workflow_preview(self) -> dict[str, Any] | None:
        if self.parsed is None or self.parsed.sequence_preparation is None: return None
        return deepcopy(self.parsed.sequence_preparation.compiled_config)

    def _sequence_model(self) -> SequenceSweepEditorModel:
        self._require_config()
        assert self.config is not None
        if self.sequence_sweep_model is None or self.sequence_sweep_model.config is not self.config:
            self.sequence_sweep_model = SequenceSweepEditorModel.load(self.config)
        return self.sequence_sweep_model

    def start_dry_run(self, event_callback: Callable[[Event], None] | None = None) -> RunViewModel:
        return self.start_run(event_callback=event_callback, connect_hardware=False)

    def start_hardware_run(self, event_callback: Callable[[Event], None] | None = None) -> RunViewModel:
        return self.start_run(event_callback=event_callback, connect_hardware=True)

    def start_run(
        self,
        event_callback: Callable[[Event], None] | None = None,
        *,
        connect_hardware: bool = False,
    ) -> RunViewModel:
        parsed = self.parsed if self.parsed is not None else self._parse_current()
        if not parsed.validation.ok:
            messages = "; ".join(issue.message for issue in parsed.validation.errors)
            raise ConfigValidationError(messages or "Config validation failed")

        self.reset_live_state()

        bus = EventBus()
        store = RunStore(
            root=self.run_root,
            experiment_name=parsed.name,
            config=parsed.config,
            resolved_config=parameter_refs_to_strings(parsed.resolved_config),
            sequence_bundles=getattr(parsed, "sequence_bundles", {}),
            sequence_preparation=getattr(parsed, "sequence_preparation", None),
            analysis_plan=getattr(parsed, "analysis_plan", None),
        )
        store.open()
        bus.subscribe(store.handle_event)
        executor = ExperimentExecutor(parsed.procedure, parsed.context, bus, dry_run=True)
        analysis_plan = getattr(parsed, "analysis_plan", None)
        engine = create_live_compute_engine(analysis_plan, None, bus) if analysis_plan is not None else None
        try:
            if engine is not None:
                engine.setup({"run_id": store.run_id, "mode": "live", "experiment": parsed.name,
                              "analysis_plan": analysis_plan.to_dict()})
                bus.subscribe(engine.handle_event)
            def live_callback(event: Event) -> None:
                self.handle_live_event(event)
                if event_callback is not None:
                    event_callback(event)
            bus.subscribe(live_callback)
            if connect_hardware:
                self._connect_resources(parsed.context.resources)
            executor.run()
        finally:
            try:
                if connect_hardware:
                    self._disconnect_resources(parsed.context.resources)
            finally:
                close_error: BaseException | None = None
                try:
                    if engine is not None:
                        try:
                            engine.close()
                        except BaseException as exc:
                            close_error = exc
                        store.set_analysis_summary(engine.summary())
                finally:
                    store.close(status="failed" if close_error is not None else (executor.state if executor.state != "created" else "failed"))
                if close_error is not None:
                    raise close_error

        self.last_run_path = store.run_path
        return RunViewModel(run_path=str(store.run_path), status=executor.state, event_count=len(bus.events))

    def reset_live_state(self, max_points: int = 1000) -> None:
        parsed = self.parsed
        with self._live_lock:
            self.live_catalog = LiveDataCatalog()
            if parsed is not None:
                raw_keys = collect_known_raw_keys(parsed.procedure)
                coord_dims = _scan_coord_names(parsed.config)
                self.live_catalog.declare_from_config(raw_keys, getattr(parsed, "analysis_plan", None), coord_dims)
            self.live_buffer = LivePointBuffer(max_points=max_points)
            self.live_plot_model = LivePlotModel(self.live_catalog, self.live_buffer)
            self.live_plot_model.initialize_defaults()
            if self._live_selected_keys is not None:
                available = {spec.key for spec in self.live_catalog.specs()}
                self.live_plot_model.select(tuple(key for key in self._live_selected_keys if key in available),
                                            **self._live_selection_options)
            self.analysis_status_model = AnalysisStatusModel(getattr(parsed, "analysis_plan", None) if parsed else None)
            self.sequence_context_model = SequenceContextModel(_single_sequence_snapshot(parsed.config if parsed else None))

    def handle_live_event(self, event: Event) -> None:
        with self._live_lock:
            self.live_catalog.handle_event(event)
            self.live_buffer.handle_event(event)
            self.analysis_status_model.handle_event(event)
            self.sequence_context_model.handle_event(event)
            self.live_plot_model.initialize_defaults()

    def get_live_data_catalog(self) -> LiveDataCatalog:
        with self._live_lock:
            return self.live_catalog.snapshot()

    def list_live_data_specs(self):
        with self._live_lock:
            return self.live_catalog.specs()

    def list_live_points(self):
        with self._live_lock:
            return self.live_buffer.points()

    def get_live_selection(self) -> LivePlotSelection:
        with self._live_lock:
            return deepcopy(self.live_plot_model.selection)

    def set_live_selection(self, keys: tuple[str, ...], *, plot_type: str = "auto",
                           x_dim: str | None = None, y_dim: str | None = None,
                           selectors: dict[str, Any] | None = None, point_id: str | None = None,
                           channel: Any | None = None) -> LivePlotSelection:
        options = {"plot_type": plot_type, "x_dim": x_dim, "y_dim": y_dim,
                   "selectors": selectors, "point_id": point_id, "channel": channel}
        with self._live_lock:
            selected = self.live_plot_model.select(keys, **options)
            self._live_selected_keys = tuple(keys)
            self._live_selection_options = options
            return deepcopy(selected)

    def clear_live_display(self) -> None:
        """Clear bounded GUI history without changing the run store or ingestion."""
        with self._live_lock:
            self.live_buffer.clear()

    def get_live_plot_data(self, selection: LivePlotSelection | None = None):
        with self._live_lock:
            return self.live_plot_model.get_plot_data(selection)

    def get_analysis_statuses(self):
        with self._live_lock:
            return self.analysis_status_model.list()

    def get_current_sequence_context(self):
        with self._live_lock:
            return self.sequence_context_model.current()

    def open_run_dataset(self, run_path: Path | str | None = None, backend: BackendPreference = "auto") -> DatasetModel:
        """Open a completed run for read-only panel preview through the storage model."""

        selected_run_path = Path(run_path) if run_path is not None else self.last_run_path
        if selected_run_path is None:
            raise RuntimeError("No run path is available yet")
        return DatasetModel(RunReader(selected_run_path, backend=backend))

    def open_historical_run(self, run_path: Path | str) -> HistoricalRunWorkspace:
        """Open a run read-only without altering the active experiment."""

        workspace = HistoricalRunWorkspace.open(run_path)
        self.historical_workspace = workspace
        self.historical_live_catalog = LiveDataCatalog()
        self.historical_live_buffer = LivePointBuffer()
        self.historical_analysis_status = AnalysisStatusModel()
        self.historical_sequence_context = SequenceContextModel()
        self.historical_replay = workspace.replay(self.handle_historical_event)
        return workspace

    def handle_historical_event(self, event: Event) -> None:
        """Feed recorded events only into dedicated read-only presentation models."""

        self.historical_live_catalog.handle_event(event)
        self.historical_live_buffer.handle_event(event)
        self.historical_analysis_status.handle_event(event)
        self.historical_sequence_context.handle_event(event)

    def clone_historical_run(self, destination: Path | str, *, use_resolved: bool = False) -> ConfigLoadResult:
        if self.historical_workspace is None:
            raise RuntimeError("No historical run is open")
        return self.historical_workspace.clone_as_draft(destination, use_resolved=use_resolved)

    def list_run_data_keys(self, run_path: Path | str | None = None, backend: BackendPreference = "auto") -> list[str]:
        return self.open_run_dataset(run_path, backend).list_data_keys()

    def get_run_line(
        self,
        data_key: str,
        x_dim: str,
        selectors: dict[str, Any] | None = None,
        run_path: Path | str | None = None,
        backend: BackendPreference = "auto",
    ) -> LineData:
        return SliceController(self.open_run_dataset(run_path, backend)).slice_1d(data_key, x_dim, selectors or {})

    def get_run_heatmap(
        self,
        data_key: str,
        x_dim: str,
        y_dim: str,
        selectors: dict[str, Any] | None = None,
        run_path: Path | str | None = None,
        backend: BackendPreference = "auto",
    ) -> HeatmapData:
        return SliceController(self.open_run_dataset(run_path, backend)).slice_2d(
            data_key, x_dim, y_dim, selectors or {}
        )

    def get_run_trace(
        self,
        data_key: str,
        point_selectors: dict[str, Any],
        channel: Any | None = None,
        run_path: Path | str | None = None,
        backend: BackendPreference = "auto",
    ) -> TraceData:
        return SliceController(self.open_run_dataset(run_path, backend)).get_point_trace(
            data_key, point_selectors, channel=channel
        )

    def current_procedure_tree_config(self) -> dict[str, Any]:
        self._require_config()
        assert self.config is not None
        return deepcopy(self.config)

    def sequence_resource_names(self) -> list[str]:
        self._require_config()
        assert self.config is not None
        resources = self.config.get("resources", {})
        if not isinstance(resources, dict):
            return []
        names: list[str] = []
        for name, resource in resources.items():
            if not isinstance(resource, dict):
                continue
            capabilities = tuple(str(item) for item in resource.get("capabilities", ()))
            adapter = str(resource.get("adapter") or "")
            if (
                "pulse_sequencer" in capabilities
                or "sequence_file" in resource
                or "sequence_params" in resource
                or "asg" in str(name).lower()
                or "asg" in adapter.lower()
            ):
                names.append(str(name))
        return names

    def get_sequence_file(self, resource_name: str = "asg") -> str:
        self._require_config()
        assert self.config is not None
        resource = self._existing_resource_config(resource_name)
        if resource is None:
            return ""
        return str(resource.get("sequence_file") or "")

    def update_sequence_file(self, resource_name: str, sequence_file: str) -> None:
        self._require_config()
        assert self.config is not None
        resource = self._resource_config(resource_name)
        resource["sequence_file"] = sequence_file
        self.parsed = None

    def get_sequence_params(self, resource_name: str = "asg") -> dict[str, Any]:
        self._require_config()
        resource = self._existing_resource_config(resource_name)
        if resource is None:
            return {}
        return deepcopy(resource.get("sequence_params") or {})

    def update_sequence_param(self, resource_name: str, name: str, value: Any) -> None:
        self._require_config()
        resource = self._resource_config(resource_name)
        params = resource.setdefault("sequence_params", {})
        if not isinstance(params, dict):
            raise TypeError(f"resources.{resource_name}.sequence_params must be a mapping")
        params[name] = value
        self.parsed = None

    def inspect_sequence_resource(self, resource_name: str = "asg") -> SequenceSnapshotViewModel:
        self._require_config()
        resource = self._existing_resource_config(resource_name) or {}
        info = inspect_sequence_file(resource.get("sequence_file"))
        params = resource.get("sequence_params") if isinstance(resource.get("sequence_params"), dict) else {}
        return SequenceSnapshotViewModel(
            resource=resource_name,
            sequence_file=info.path,
            exists=info.exists,
            mtime=info.mtime,
            size_bytes=info.size_bytes,
            sha256=info.sha256,
            parameters=tuple(info.parameters),
            channels=tuple(info.channels),
            preview_lines=tuple(getattr(info, "preview_lines", ())),
            sequence_params=deepcopy(params),
            warnings=tuple(info.warnings),
        )

    def inspect_sequence_references(self) -> list[SequenceSnapshotViewModel]:
        self._require_config()
        assert self.config is not None
        snapshots: list[SequenceSnapshotViewModel] = []
        for reference in discover_sequence_references(self.config):
            info = inspect_sequence_file(reference.sequence_file)
            resource = self._existing_resource_config(reference.resource) or {}
            params = resource.get("sequence_params") if isinstance(resource.get("sequence_params"), dict) else {}
            snapshots.append(
                SequenceSnapshotViewModel(
                    resource=reference.resource,
                    sequence_file=info.path,
                    exists=info.exists,
                    reference_id=reference.reference_id,
                    label=reference.label,
                    source=reference.source,
                    mtime=info.mtime,
                    size_bytes=info.size_bytes,
                    sha256=info.sha256,
                    parameters=tuple(info.parameters),
                    channels=tuple(info.channels),
                    preview_lines=tuple(getattr(info, "preview_lines", ())),
                    sequence_params=deepcopy(params),
                    warnings=tuple(info.warnings),
                )
            )
        return snapshots

    def workflow_tree(self):
        self._require_config()
        assert self.config is not None
        return build_workflow_tree(self.config)

    def workflow_composer(self) -> WorkflowComposerModel:
        self._require_config()
        assert self.config is not None
        if self._workflow_composer is None or self._workflow_composer.config is not self.config:
            self._workflow_composer = WorkflowComposerModel(self.config)
        return self._workflow_composer

    def sequence_authoring(self) -> SequenceAuthoringModel:
        self._require_config()
        assert self.config is not None
        sweep = self._sequence_model()
        if self._sequence_authoring is None or self._sequence_authoring.config is not self.config:
            self._sequence_authoring = SequenceAuthoringModel(self.config, sweep)
        return self._sequence_authoring

    def get_guided_sequence_state(self, plan_id: str | None = None, *, include_previews: bool = False,
                                  current_index: int | None = None) -> GuidedSequenceViewState:
        return SequenceAuthoringPresenter(self.sequence_authoring()).state(plan_id, include_previews=include_previews,
                                                                          current_index=current_index)

    def preview_sequence_mode_change(self, plan_id: str, new_mode: str):
        return self.sequence_authoring().preview_mode_change(plan_id, new_mode)

    def change_sequence_mode(self, plan_id: str, new_mode: str, *, provider: str | None = None,
                             template: str | None = None) -> GuidedSequenceViewState:
        self.sequence_authoring().change_mode(plan_id, new_mode, provider=provider, template=template)
        self._sequence_edited(plan_id); return self.get_guided_sequence_state(plan_id)

    def change_sequence_resource(self, plan_id: str, resource: str) -> GuidedSequenceViewState:
        if resource not in self.sequence_resource_names():
            raise ValueError(f"Resource '{resource}' does not declare pulse_sequencer capability")
        self.sequence_authoring().update_resource(plan_id, resource)
        self._sequence_edited(plan_id); return self.get_guided_sequence_state(plan_id)

    def update_sequence_roles(self, plan_id: str, roles: dict[str, str], *, confirmed: bool = True) -> None:
        self.sequence_authoring().update_roles(plan_id, roles, confirmed=confirmed); self._sequence_edited(plan_id)

    def update_sequence_target_transform(self, plan_id: str, alias: str, channel: str, pulse: int, **options: Any) -> None:
        self.sequence_authoring().update_target_transform(plan_id, alias, channel, pulse, **options); self._sequence_edited(plan_id)

    def add_sequence_anchor(self, plan_id: str, target: str, reference: str, offset_s: float = 0.0) -> None:
        self.sequence_authoring().add_anchor_constraint(plan_id, target, reference, offset_s); self._sequence_edited(plan_id)

    def get_sequence_previews(self, plan_id: str, current_index: int | None = None):
        return self.sequence_authoring().normalized_previews(plan_id, current_index)

    def get_sequence_provenance(self, plan_id: str) -> dict[str, Any] | None:
        preparation = getattr(self.parsed, "sequence_preparation", None) if self.parsed is not None else None
        if preparation is None or plan_id not in preparation.materialized: return None
        bundle = preparation.materialized[plan_id]
        record = next((item for item in preparation.generation_records if item.plan_id == plan_id), None)
        result = bundle.to_dict()
        if record is not None: result["generation_record"] = record.to_dict()
        result["compiled_workflow"] = deepcopy(preparation.compiled_config.get("procedure", []))
        result["runstore_provenance"] = {
            "sequence_generation": "metadata.json",
            "sequence_plan": f"artifacts/sequence_generation/{plan_id}/sequence_plan.yaml",
            "provider_identity": f"artifacts/sequence_generation/{plan_id}/provider_identity.json",
        }
        return result

    def validate_sequence_plan(self, plan_id: str):
        return self.sequence_authoring().located_issues(plan_id)

    def insert_sequence_macro(self, plan_id: str, parent: tuple[str | int, ...] = ("procedure",),
                              index: int | None = None):
        path = self.sequence_authoring().insert_or_update_macro(plan_id, parent, index)
        self._sequence_edited(plan_id); return path

    def accept_sequence_editor_result(self, plan_id: str, saved_artifact: dict[str, Any] | None) -> None:
        self.sequence_authoring().accept_editor_result(plan_id, saved_artifact); self._sequence_edited(plan_id)

    def mark_sequence_template_stale(self, plan_id: str) -> None:
        self._sequence_model()._edited(plan_id); self._sequence_edited(plan_id)

    def _sequence_edited(self, plan_id: str) -> None:
        self.parsed = None; self._sequence_prepared_revisions.pop(plan_id, None)

    def update_workflow_node(self, path: WorkflowPath, patch: dict[str, Any]) -> None:
        self._require_config()
        assert self.config is not None
        self.config = update_node(self.config, path, patch)
        self.parsed = None

    def add_workflow_step(self, parent_path: WorkflowPath, step: dict[str, Any]) -> None:
        self._require_config()
        assert self.config is not None
        self.config = add_step(self.config, parent_path, step)
        self.parsed = None

    def delete_workflow_step(self, path: WorkflowPath) -> None:
        self._require_config()
        assert self.config is not None
        self.config = delete_step(self.config, path)
        self.parsed = None

    def duplicate_workflow_step(self, path: WorkflowPath) -> None:
        self._require_config()
        assert self.config is not None
        self.config = duplicate_step(self.config, path)
        self.parsed = None

    def _parse_current(self) -> ParsedExperiment:
        self._require_config()
        assert self.config is not None
        try:
            self.parsed = prepare_and_parse_experiment_config(deepcopy(self.config))
        except SequenceGenerationError as exc:
            raise ConfigValidationError(f"[{exc.code}] {exc}") from exc
        return self.parsed

    def _preflight_view(self, parsed: ParsedExperiment) -> PreflightViewModel:
        resources: list[ResourceViewModel] = []
        raw_resources = parsed.resolved_config.get("resources", {})
        for name, resource in parsed.context.resources.items():
            snapshot = resource.snapshot()
            health = resource.health_check()
            raw_config = raw_resources.get(name, {}) if isinstance(raw_resources, dict) else {}
            resources.append(
                ResourceViewModel(
                    name=name,
                    adapter=str(snapshot.get("adapter") or raw_config.get("adapter") or ""),
                    capabilities=tuple(snapshot.get("capabilities", ())),
                    connect_on_load=bool(raw_config.get("connect_on_load", False)),
                    connected=bool(snapshot.get("connected", False)),
                    simulation=bool(snapshot.get("simulation", True)),
                    health=health,
                    snapshot=snapshot,
                )
            )
        issues = tuple(
            PreflightIssueViewModel(issue.severity, issue.code, issue.message) for issue in parsed.validation.issues
        )
        sequence_snapshots = tuple(self.inspect_sequence_references())
        return PreflightViewModel(
            ok=parsed.validation.ok,
            resources=tuple(resources),
            issues=issues,
            sequence_snapshots=sequence_snapshots,
        )

    def _resource_config(self, resource_name: str) -> dict[str, Any]:
        self._require_config()
        assert self.config is not None
        resources = self.config.setdefault("resources", {})
        if not isinstance(resources, dict):
            raise TypeError("resources must be a mapping")
        resource = resources.setdefault(resource_name, {})
        if not isinstance(resource, dict):
            raise TypeError(f"resources.{resource_name} must be a mapping")
        return resource

    def _existing_resource_config(self, resource_name: str) -> dict[str, Any] | None:
        self._require_config()
        assert self.config is not None
        resources = self.config.get("resources", {})
        if not isinstance(resources, dict):
            raise TypeError("resources must be a mapping")
        resource = resources.get(resource_name)
        if resource is None:
            return None
        if not isinstance(resource, dict):
            raise TypeError(f"resources.{resource_name} must be a mapping")
        return resource

    def _require_config(self) -> None:
        if self.config is None:
            raise RuntimeError("No experiment config loaded")

    def _connect_resources(self, resources: dict[str, Any]) -> None:
        connected: list[Any] = []
        try:
            for resource in resources.values():
                if getattr(resource, "simulation", False):
                    continue
                resource.connect()
                connected.append(resource)
        except BaseException:
            for resource in reversed(connected):
                try:
                    resource.disconnect()
                except Exception:
                    pass
            raise

    def _disconnect_resources(self, resources: dict[str, Any]) -> None:
        first_error: BaseException | None = None
        for resource in reversed(list(resources.values())):
            if getattr(resource, "simulation", False):
                continue
            try:
                resource.disconnect()
            except BaseException as exc:
                if first_error is None:
                    first_error = exc
        if first_error is not None:
            raise first_error


def _scan_coord_names(config: dict[str, Any] | None) -> tuple[str, ...]:
    names: list[str] = []
    def walk(steps: Any) -> None:
        if not isinstance(steps, list): return
        for step in steps:
            if not isinstance(step, dict): continue
            for kind in ("scan", "average"):
                payload = step.get(kind)
                if isinstance(payload, dict):
                    name = payload.get("name")
                    if isinstance(name, str) and name not in names: names.append(name)
                    walk(payload.get("body"))
            for kind in ("measurement", "run"):
                payload = step.get(kind)
                if isinstance(payload, dict): walk(payload.get("body", payload.get("steps")))
    if config:
        walk(config.get("procedure"))
    return tuple(names)


def _single_sequence_snapshot(config: dict[str, Any] | None) -> dict[str, Any] | None:
    if not config: return None
    resources = config.get("resources", {})
    if not isinstance(resources, dict): return None
    for name, resource in resources.items():
        if isinstance(resource, dict) and (resource.get("sequence_file") or resource.get("sequence_path")):
            return {"resource": name, "sequence_file": resource.get("sequence_file") or resource.get("sequence_path")}
    return None
