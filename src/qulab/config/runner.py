"""Convenience runner for YAML dry-run experiments."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qulab.core import EventBus, ExperimentExecutor
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
    )
    store.open()
    bus.subscribe(store.handle_event)
    executor = ExperimentExecutor(parsed.procedure, parsed.context, bus, dry_run=True)
    try:
        executor.run()
    finally:
        store.close(status=executor.state)

    return RunResult(
        parsed=parsed,
        run_path=store.run_path,
        executor_state=executor.state,
        events=list(bus.events),
        validation=parsed.validation,
    )
