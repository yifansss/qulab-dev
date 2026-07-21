"""Dry-run executor for procedure step trees."""

from __future__ import annotations

import time
from typing import Any, Callable

from .context import ExperimentContext
from .events import (
    DataPoint,
    ErrorRaised,
    EventBus,
    MeasurementCompleted,
    MeasurementStarted,
    ParameterChanged,
    RunCompleted,
    RunStarted,
    StepCompleted,
    StepStarted,
)
from .procedure import (
    ActionStep,
    AverageStep,
    CleanupStep,
    MeasurementStep,
    Procedure,
    RunStep,
    ScanStep,
    Step,
    WaitStep,
)


class ExperimentExecutor:
    """Execute a Procedure against an ExperimentContext and emit events."""

    def __init__(
        self,
        procedure: Procedure,
        context: ExperimentContext | None = None,
        event_bus: EventBus | None = None,
        dry_run: bool = True,
    ) -> None:
        self.procedure = procedure
        self.context = context or ExperimentContext()
        self.event_bus = event_bus or EventBus()
        self.dry_run = dry_run
        self.state = "created"
        self.run_id = procedure.name

    def run(self) -> None:
        self.state = "running"
        self.event_bus.emit(RunStarted(run_id=self.run_id, procedure_name=self.procedure.name))
        failure: BaseException | None = None

        try:
            self._execute_steps(self.procedure.setup)
            self._execute_steps(self.procedure.body)
            self.state = "completed"
        except BaseException as exc:
            failure = exc
            self.state = "failed"
        finally:
            cleanup_failure = self._run_cleanup()
            if cleanup_failure is not None and failure is None:
                failure = cleanup_failure
                self.state = "failed"
            self.event_bus.emit(RunCompleted(run_id=self.run_id, status=self.state))

        if failure is not None:
            raise failure

    def _run_cleanup(self) -> BaseException | None:
        try:
            self._execute_steps(self.procedure.cleanup)
        except BaseException as exc:
            return exc
        return None

    def _execute_steps(self, steps: list[Step]) -> None:
        for step in steps:
            self._execute_step(step)

    def _execute_step(self, step: Step) -> None:
        if not step.enabled:
            return

        self.event_bus.emit(
            StepStarted(
                step_id=step.id or "",
                step_name=step.name,
                step_kind=step.kind,
                point_id=self.context.current_point_id,
                coords=self.context.snapshot_coords(),
            )
        )
        try:
            self._dispatch_step(step)
        except BaseException as exc:
            self.event_bus.emit(
                ErrorRaised(
                    error_type=type(exc).__name__,
                    message=str(exc),
                    step_id=step.id,
                )
            )
            self.event_bus.emit(
                StepCompleted(
                    step_id=step.id or "",
                    step_name=step.name,
                    step_kind=step.kind,
                    status="failed",
                    point_id=self.context.current_point_id,
                    coords=self.context.snapshot_coords(),
                )
            )
            raise

        self.event_bus.emit(
            StepCompleted(
                step_id=step.id or "",
                step_name=step.name,
                step_kind=step.kind,
                status="ok",
                point_id=self.context.current_point_id,
                coords=self.context.snapshot_coords(),
            )
        )

    def _dispatch_step(self, step: Step) -> None:
        if isinstance(step, ActionStep):
            self._execute_action(step)
        elif isinstance(step, ScanStep):
            self._execute_scan(step)
        elif isinstance(step, AverageStep):
            self._execute_average(step)
        elif isinstance(step, MeasurementStep):
            self._execute_measurement(step)
        elif isinstance(step, RunStep):
            self._execute_steps(step.body)
        elif isinstance(step, WaitStep):
            self._execute_wait(step)
        elif isinstance(step, CleanupStep):
            self._execute_steps(step.body)
        else:
            raise TypeError(f"Unsupported step type: {type(step).__name__}")

    def _execute_action(self, step: ActionStep) -> None:
        args = self.context.resolve(step.args)
        kwargs = self.context.resolve(step.kwargs)
        if isinstance(step.action, str) and step.action.endswith(".load_sequence_from_bundle"):
            if args:
                raise TypeError("load_sequence_from_bundle accepts keyword arguments only")
            resource_name, method_name = step.action.split(".", 1)
            if method_name != "load_sequence_from_bundle":
                raise ValueError(f"Unsupported bundle action: {step.action}")
            from qulab.sequence_runtime import load_sequence_from_bundle

            result = load_sequence_from_bundle(
                self.context,
                self.event_bus,
                resource_name=resource_name,
                **kwargs,
            )
        else:
            action = self._resolve_action(step.action)
            result = action(*args, **kwargs) if action is not None else None

        if step.save_as:
            self.event_bus.emit(
                DataPoint(
                    point_id=self.context.current_point_id,
                    coords=self.context.snapshot_coords(),
                    data={step.save_as: result},
                    metadata={"step_id": step.id, "step_name": step.name},
                )
            )

    def _resolve_action(self, action: Callable[..., Any] | str | None) -> Callable[..., Any] | None:
        if action is None or callable(action):
            return action
        if "." not in action:
            raise ValueError(f"Action string must be '<resource>.<method>': {action}")
        resource_name, method_name = action.split(".", 1)
        if resource_name not in self.context.resources:
            raise KeyError(f"Unknown resource: {resource_name}")
        method = getattr(self.context.resources[resource_name], method_name)
        if not callable(method):
            raise TypeError(f"Resource method is not callable: {action}")
        return method

    def _execute_scan(self, step: ScanStep) -> None:
        previous_parameter = self.context.parameters.get(step.name)
        had_coord = step.name in self.context.coords
        previous_coord = self.context.coords.get(step.name)

        try:
            for value in step.values:
                self.context.set_parameter(step.name, value)
                self.context.coords[step.name] = value
                self.event_bus.emit(
                    ParameterChanged(
                        name=step.name,
                        value=value,
                        coords=self.context.snapshot_coords(),
                    )
                )
                self._execute_steps(step.body)
        finally:
            if previous_parameter is None:
                self.context.parameters.pop(step.name, None)
            else:
                self.context.parameters[step.name] = previous_parameter

            if had_coord:
                self.context.coords[step.name] = previous_coord
            else:
                self.context.coords.pop(step.name, None)

    def _execute_average(self, step: AverageStep) -> None:
        if step.count < 0:
            raise ValueError("average count must be non-negative")

        previous_parameter = self.context.parameters.get(step.name)
        had_coord = step.name in self.context.coords
        previous_coord = self.context.coords.get(step.name)

        try:
            for index in range(step.count):
                self.context.set_parameter(step.name, index)
                self.context.coords[step.name] = index
                self.event_bus.emit(
                    ParameterChanged(
                        name=step.name,
                        value=index,
                        coords=self.context.snapshot_coords(),
                    )
                )
                self._execute_steps(step.body)
        finally:
            if previous_parameter is None:
                self.context.parameters.pop(step.name, None)
            else:
                self.context.parameters[step.name] = previous_parameter

            if had_coord:
                self.context.coords[step.name] = previous_coord
            else:
                self.context.coords.pop(step.name, None)

    def _execute_measurement(self, step: MeasurementStep) -> None:
        previous_point_id = self.context.current_point_id
        point_id = self.context.next_point_id()
        self.context.current_point_id = point_id
        self.event_bus.emit(MeasurementStarted(point_id=point_id, coords=self.context.snapshot_coords()))

        try:
            self._execute_steps(step.body)
        except BaseException:
            self.event_bus.emit(
                MeasurementCompleted(
                    point_id=point_id,
                    status="failed",
                    coords=self.context.snapshot_coords(),
                )
            )
            raise
        else:
            self.event_bus.emit(
                MeasurementCompleted(
                    point_id=point_id,
                    status="ok",
                    coords=self.context.snapshot_coords(),
                )
            )
        finally:
            self.context.current_point_id = previous_point_id

    def _execute_wait(self, step: WaitStep) -> None:
        if step.duration_s < 0:
            raise ValueError("wait duration_s must be non-negative")
        if not self.dry_run and step.duration_s > 0:
            time.sleep(step.duration_s)
