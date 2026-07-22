"""Convenience runner for YAML dry-run experiments."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qulab.core import EventBus, ExperimentExecutor
from qulab.analysis import create_live_compute_engine
from qulab.storage import RunStore

from .errors import ConfigValidationError
from .loader import load_experiment_config
from .parser import ParsedExperiment, parse_experiment_config
from .refs import parameter_refs_to_strings
from qulab.sequence_generation import SequenceGenerationError, prepare_and_parse_experiment_config


@dataclass
class RunResult:
    parsed: ParsedExperiment
    run_path: Path
    executor_state: str
    events: list[Any]
    validation: Any
    analysis_summary: dict[str, Any] | None = None


def run_dry_config(config_source: str | Path | dict[str, Any], run_root: str | Path) -> RunResult:
    """Load, preflight, execute, and store a dry-run experiment config."""

    config = load_experiment_config(config_source)
    try:
        parsed = prepare_and_parse_experiment_config(config)
    except SequenceGenerationError as exc:
        raise ConfigValidationError(f"[{exc.code}] {exc}") from exc
    if not parsed.validation.ok:
        messages = "; ".join(issue.message for issue in parsed.validation.errors)
        raise ConfigValidationError(messages or "Config validation failed")

    bus = EventBus()
    store = RunStore(
        root=run_root,
        experiment_name=parsed.name,
        config=parsed.config,
        resolved_config=parameter_refs_to_strings(parsed.resolved_config),
        sequence_bundles=parsed.sequence_bundles,
        sequence_preparation=parsed.sequence_preparation,
        analysis_plan=parsed.analysis_plan,
    )
    store.open()
    bus.subscribe(store.handle_event)
    executor = ExperimentExecutor(parsed.procedure, parsed.context, bus, dry_run=True)
    engine = create_live_compute_engine(parsed.analysis_plan, None, bus) if parsed.analysis_plan is not None else None
    try:
        if engine is not None:
            engine.setup({"run_id": store.run_id, "mode": "live", "experiment": parsed.name,
                          "analysis_plan": parsed.analysis_plan.to_dict()})
            bus.subscribe(engine.handle_event)
        executor.run()
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

    return RunResult(
        parsed=parsed,
        run_path=store.run_path,
        executor_state=executor.state,
        events=list(bus.events),
        validation=parsed.validation,
        analysis_summary=engine.summary() if engine is not None else None,
    )
