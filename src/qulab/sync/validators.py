"""Preflight validation for sync plans and procedure basics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from qulab.core import ActionStep, AverageStep, ExperimentContext, Procedure, RunStep, ScanStep, Step

from .trigger_plan import SyncPlan


@dataclass(frozen=True)
class SyncValidationIssue:
    severity: str
    code: str
    message: str


@dataclass
class SyncValidationResult:
    issues: list[SyncValidationIssue]

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def errors(self) -> list[SyncValidationIssue]:
        return [issue for issue in self.issues if issue.severity == "error"]

    @property
    def warnings(self) -> list[SyncValidationIssue]:
        return [issue for issue in self.issues if issue.severity == "warning"]


class SyncValidator:
    """Validate obvious dry-run sync and procedure mistakes."""

    _VALID_EDGES = {"rising", "falling", "both"}

    def validate(
        self,
        sync_plan: SyncPlan | None,
        context: ExperimentContext,
        procedure: Procedure,
    ) -> SyncValidationResult:
        issues: list[SyncValidationIssue] = []
        resources = set(context.resources)

        if sync_plan is None:
            if any(isinstance(step, RunStep) for step in _walk_steps(procedure.body)):
                issues.append(
                    SyncValidationIssue("warning", "sync_missing", "Procedure has run steps but no sync plan")
                )
        else:
            self._validate_plan(sync_plan, resources, issues)
            self._validate_procedure_order(sync_plan, procedure, issues)

        for step in _walk_steps([*procedure.setup, *procedure.body, *procedure.cleanup]):
            if isinstance(step, ScanStep) and len(step.values) == 0:
                issues.append(SyncValidationIssue("error", "empty_scan", f"Scan '{step.name}' has no values"))
            if isinstance(step, AverageStep) and step.count <= 0:
                issues.append(
                    SyncValidationIssue("error", "invalid_average", f"Average '{step.name}' count must be > 0")
                )

        return SyncValidationResult(issues)

    def _validate_plan(
        self,
        sync_plan: SyncPlan,
        resources: set[str],
        issues: list[SyncValidationIssue],
    ) -> None:
        if sync_plan.master and sync_plan.master not in resources:
            issues.append(
                SyncValidationIssue("error", "unknown_master", f"Sync master resource does not exist: {sync_plan.master}")
            )

        for trigger in sync_plan.triggers:
            source_resource = self._validate_endpoint(trigger.source, "source", resources, issues)
            target_resource = self._validate_endpoint(trigger.target, "target", resources, issues)
            if trigger.edge not in self._VALID_EDGES:
                issues.append(
                    SyncValidationIssue("error", "invalid_edge", f"Invalid trigger edge '{trigger.edge}'")
                )
            if source_resource and target_resource and source_resource == target_resource:
                issues.append(
                    SyncValidationIssue(
                        "warning", "self_trigger", f"Trigger source and target use the same resource: {source_resource}"
                    )
                )

        if sync_plan.order is None:
            return

        for phase, names in (
            ("configure", sync_plan.order.configure),
            ("arm", sync_plan.order.arm),
            ("start", sync_plan.order.start),
            ("read", sync_plan.order.read),
        ):
            for name in names:
                if name not in resources:
                    issues.append(
                        SyncValidationIssue("error", "unknown_order_resource", f"Unknown resource in {phase}: {name}")
                    )

        self._validate_arm_before_start(sync_plan, issues)

    def _validate_endpoint(
        self,
        endpoint: str,
        role: str,
        resources: set[str],
        issues: list[SyncValidationIssue],
    ) -> str | None:
        if not isinstance(endpoint, str) or "." not in endpoint:
            issues.append(
                SyncValidationIssue("error", "invalid_trigger_endpoint", f"Trigger {role} must be resource.channel")
            )
            return None
        resource, channel = endpoint.split(".", 1)
        if not resource or not channel:
            issues.append(
                SyncValidationIssue("error", "invalid_trigger_endpoint", f"Trigger {role} must be resource.channel")
            )
            return None
        if resource not in resources:
            issues.append(
                SyncValidationIssue("error", "unknown_trigger_resource", f"Unknown trigger {role} resource: {resource}")
            )
        return resource

    def _validate_arm_before_start(self, sync_plan: SyncPlan, issues: list[SyncValidationIssue]) -> None:
        assert sync_plan.order is not None
        arm = sync_plan.order.arm
        start = sync_plan.order.start
        if not arm or not start:
            return

        receiver_names = {trigger.target.split(".", 1)[0] for trigger in sync_plan.triggers if "." in trigger.target}
        source_names = {trigger.source.split(".", 1)[0] for trigger in sync_plan.triggers if "." in trigger.source}
        for receiver in receiver_names:
            for source in source_names:
                if receiver in arm and source in arm and arm.index(receiver) > arm.index(source):
                    issues.append(
                        SyncValidationIssue(
                            "error",
                            "receiver_arm_order",
                            f"Receiver '{receiver}' should be armed before trigger source '{source}'",
                        )
                    )
                if receiver not in arm and source in start:
                    issues.append(
                        SyncValidationIssue(
                            "warning",
                            "receiver_not_armed",
                            f"Receiver '{receiver}' is not listed in arm order before '{source}' starts",
                        )
                    )

    def _validate_procedure_order(
        self,
        sync_plan: SyncPlan,
        procedure: Procedure,
        issues: list[SyncValidationIssue],
    ) -> None:
        """Ensure executable run blocks do not contradict declarative sync order."""

        if sync_plan.order is None:
            return
        declared = {
            "arm": sync_plan.order.arm,
            "start": sync_plan.order.start,
            "read": sync_plan.order.read,
        }
        for run in (step for step in _walk_steps(procedure.body) if isinstance(step, RunStep)):
            phase_resources: dict[str, list[str]] = {"arm": [], "start": [], "read": []}
            for step in _walk_steps(run.body):
                if not isinstance(step, ActionStep) or not isinstance(step.action, str) or "." not in step.action:
                    continue
                resource, method = step.action.split(".", 1)
                phase = (
                    "arm" if method == "arm"
                    else "start" if method in {"start", "play"}
                    else "read" if method == "read" or method.startswith("read_")
                    else None
                )
                if phase is not None and resource not in phase_resources[phase]:
                    phase_resources[phase].append(resource)
            for phase, actual in phase_resources.items():
                expected = [name for name in declared[phase] if name in actual]
                if len(actual) > 1 and actual != expected:
                    issues.append(
                        SyncValidationIssue(
                            "error",
                            "procedure_sync_order_mismatch",
                            f"Run '{run.name}' executes {phase} order {actual}, "
                            f"but sync.order.{phase} declares {declared[phase]}",
                        )
                    )
def _walk_steps(steps: Iterable[Step]) -> Iterable[Step]:
    for step in steps:
        yield step
        body = getattr(step, "body", None)
        if body:
            yield from _walk_steps(body)
