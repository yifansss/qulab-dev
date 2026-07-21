"""Static workflow preflight for sequence bundle actions."""

from __future__ import annotations

import itertools
import math
from collections.abc import Iterable, Mapping
from typing import Any

from qulab.core import ActionStep, ExperimentContext, ParameterRef, Procedure, ScanStep, Step
from qulab.sequence_bundles import SequenceBundle, SequenceBundleError
from qulab.sync import SyncPlan, SyncValidationIssue


DEFAULT_COVERAGE_LIMIT = 10_000
_ACQUISITION_METHODS = {
    "configure_ai",
    "configure_ai_external_trigger",
    "configure_counter",
    "configure_counter_external_clock",
}


class SequenceBundlePreflightValidator:
    """Validate statically enumerable bundle selections and coarse sync metadata."""

    def __init__(self, coverage_limit: int = DEFAULT_COVERAGE_LIMIT) -> None:
        self.coverage_limit = coverage_limit

    def validate(
        self,
        sync_plan: SyncPlan | None,
        context: ExperimentContext,
        procedure: Procedure,
    ) -> list[SyncValidationIssue]:
        issues: list[SyncValidationIssue] = []
        all_steps = [*procedure.setup, *procedure.body, *procedure.cleanup]
        acquisition_actions = [
            step
            for step in _walk_steps(all_steps)
            if isinstance(step, ActionStep) and _method_name(step) in _ACQUISITION_METHODS
        ]
        for action, scan_domains in _bundle_actions(all_steps):
            self._validate_action(
                action,
                scan_domains,
                acquisition_actions,
                sync_plan,
                context,
                issues,
            )
        return _dedupe_issues(issues)

    def _validate_action(
        self,
        action: ActionStep,
        scan_domains: Mapping[str, tuple[Any, ...]],
        acquisition_actions: list[ActionStep],
        sync_plan: SyncPlan | None,
        context: ExperimentContext,
        issues: list[SyncValidationIssue],
    ) -> None:
        assert isinstance(action.action, str)
        resource_name = action.action.split(".", 1)[0]
        raw_bundle_id = action.kwargs.get("bundle")
        if not isinstance(raw_bundle_id, str):
            issues.append(
                SyncValidationIssue(
                    "error",
                    "bundle_id_invalid",
                    f"Action '{action.name}' must use a literal sequence bundle id",
                )
            )
            return
        if raw_bundle_id not in context.sequence_bundles:
            issues.append(
                SyncValidationIssue(
                    "error",
                    "bundle_unknown",
                    f"Action '{action.name}' references unknown sequence bundle '{raw_bundle_id}'",
                )
            )
            return
        bundle = context.sequence_bundles[raw_bundle_id]
        if bundle.resource != resource_name:
            issues.append(
                SyncValidationIssue(
                    "error",
                    "bundle_resource_mismatch",
                    f"Action resource '{resource_name}' does not match bundle '{bundle.id}' resource "
                    f"'{bundle.resource}'",
                )
            )
            return

        planned = self._planned_selections(action, scan_domains, bundle, issues)
        if planned is None:
            entries = list(bundle.entries)
        else:
            entries = []
            seen: set[str] = set()
            for selection in planned:
                if selection.entry_id not in seen:
                    seen.add(selection.entry_id)
                    entries.append(next(entry for entry in bundle.entries if entry.id == selection.entry_id))
        if not entries:
            return
        relevant_acquisition_actions = acquisition_actions
        if sync_plan is not None:
            target_resources = {
                trigger.target.split(".", 1)[0]
                for trigger in sync_plan.triggers
                if trigger.source.lower().startswith(f"{resource_name.lower()}.") and "." in trigger.target
            }
            if target_resources:
                relevant_acquisition_actions = [
                    candidate
                    for candidate in acquisition_actions
                    if str(candidate.action).split(".", 1)[0] in target_resources
                ]
        self._validate_trigger_metadata(
            bundle,
            resource_name,
            entries,
            relevant_acquisition_actions,
            sync_plan,
            issues,
        )
        self._validate_acquisition_windows(bundle, entries, relevant_acquisition_actions, issues)
        self._validate_routes(resource_name, relevant_acquisition_actions, sync_plan, issues)

    def _planned_selections(
        self,
        action: ActionStep,
        scan_domains: Mapping[str, tuple[Any, ...]],
        bundle: SequenceBundle,
        issues: list[SyncValidationIssue],
    ) -> list[Any] | None:
        coordinates = action.kwargs.get("coordinates", {})
        if not isinstance(coordinates, Mapping):
            issues.append(
                SyncValidationIssue(
                    "error",
                    "bundle_coordinates_invalid",
                    f"Bundle '{bundle.id}' action coordinates must be a mapping",
                )
            )
            return []
        entry_id = action.kwargs.get("entry_id")
        dynamic_names: set[str] = set()
        for value in [*coordinates.values(), entry_id]:
            if isinstance(value, ParameterRef):
                dynamic_names.add(value.name)
        missing_names = sorted(name for name in dynamic_names if name not in scan_domains)
        if missing_names:
            issues.append(
                SyncValidationIssue(
                    "warning",
                    "bundle_coverage_dynamic",
                    f"Bundle '{bundle.id}' coverage cannot be proven because parameters are not statically "
                    f"scanned here: {', '.join(missing_names)}",
                )
            )
            return None

        domain_names = sorted(dynamic_names)
        point_count = math.prod(len(scan_domains[name]) for name in domain_names) if domain_names else 1
        if point_count > self.coverage_limit:
            issues.append(
                SyncValidationIssue(
                    "warning",
                    "bundle_coverage_limit",
                    f"Bundle '{bundle.id}' planned coverage has {point_count} points, above the static "
                    f"limit {self.coverage_limit}; runtime validation remains enabled",
                )
            )
            return None

        selections: list[Any] = []
        domains = [scan_domains[name] for name in domain_names]
        assignments = itertools.product(*domains) if domains else [()]
        for values in assignments:
            parameters = dict(zip(domain_names, values))
            requested = {
                str(name): parameters[value.name] if isinstance(value, ParameterRef) else value
                for name, value in coordinates.items()
            }
            resolved_entry_id = parameters[entry_id.name] if isinstance(entry_id, ParameterRef) else entry_id
            try:
                selection = bundle.resolve(
                    requested,
                    entry_id=resolved_entry_id,
                    mode=action.kwargs.get("mode"),
                    tolerance=action.kwargs.get("tolerance"),
                )
            except SequenceBundleError as exc:
                code = getattr(exc, "code", "invalid")
                issue_code = {
                    "no_match": "bundle_coverage_missing",
                    "ambiguous_match": "bundle_coverage_ambiguous",
                }.get(code, "bundle_coverage_invalid")
                issues.append(
                    SyncValidationIssue(
                        "error",
                        issue_code,
                        f"Bundle '{bundle.id}' cannot resolve planned coordinates {requested!r}: {exc}",
                    )
                )
            else:
                selections.append(selection)
        return selections

    def _validate_trigger_metadata(
        self,
        bundle: SequenceBundle,
        resource_name: str,
        entries: list[Any],
        acquisition_actions: list[ActionStep],
        sync_plan: SyncPlan | None,
        issues: list[SyncValidationIssue],
    ) -> None:
        declared = {
            _normalize_channel(channel)
            for entry in entries
            for channel in entry.metadata.get("trigger_channels", [])
        }
        if not declared:
            issues.append(
                SyncValidationIssue(
                    "warning",
                    "bundle_trigger_metadata_missing",
                    f"Bundle '{bundle.id}' entries do not provide trigger_channels metadata",
                )
            )
            return
        configured = {
            _normalize_channel(trigger.source.split(".", 1)[1])
            for trigger in (sync_plan.triggers if sync_plan else [])
            if trigger.source.lower().startswith(f"{resource_name.lower()}.")
        }
        missing = sorted(declared - configured)
        if not missing:
            return
        has_start_trigger = any(
            action.kwargs.get("start_trigger") is not None or action.kwargs.get("trigger") is not None
            for action in acquisition_actions
        )
        severity = "error" if has_start_trigger else "warning"
        issues.append(
            SyncValidationIssue(
                severity,
                "bundle_trigger_channel_mismatch",
                f"Bundle '{bundle.id}' trigger channel(s) {missing} are not declared as sync sources for "
                f"resource '{resource_name}'",
            )
        )

    def _validate_acquisition_windows(
        self,
        bundle: SequenceBundle,
        entries: list[Any],
        acquisition_actions: list[ActionStep],
        issues: list[SyncValidationIssue],
    ) -> None:
        requirements: list[float] = []
        for entry in entries:
            value = None
            for key in ("required_acquisition_s", "readout_window_s", "duration_s"):
                if key in entry.metadata:
                    value = entry.metadata[key]
                    break
            if value is not None:
                try:
                    number = float(value)
                except (TypeError, ValueError):
                    number = -1.0
                if number <= 0 or not math.isfinite(number):
                    issues.append(
                        SyncValidationIssue(
                            "error",
                            "bundle_duration_invalid",
                            f"Bundle '{bundle.id}' entry '{entry.id}' acquisition duration must be finite and positive",
                        )
                    )
                else:
                    requirements.append(number)
        if not requirements:
            issues.append(
                SyncValidationIssue(
                    "warning",
                    "bundle_duration_metadata_missing",
                    f"Bundle '{bundle.id}' entries do not provide acquisition duration metadata",
                )
            )
            return
        if not acquisition_actions:
            issues.append(
                SyncValidationIssue(
                    "warning",
                    "bundle_acquisition_window_unknown",
                    f"Bundle '{bundle.id}' has duration metadata but no static DAQ configure action was found",
                )
            )
            return
        required = max(requirements)
        found_literal = False
        for action in acquisition_actions:
            sample_rate = action.kwargs.get("sample_rate")
            samples = action.kwargs.get("samples")
            if isinstance(sample_rate, ParameterRef) or isinstance(samples, ParameterRef):
                continue
            if not isinstance(sample_rate, (int, float)) or isinstance(sample_rate, bool):
                continue
            if not isinstance(samples, (int, float)) or isinstance(samples, bool):
                continue
            found_literal = True
            if sample_rate <= 0 or samples <= 0:
                issues.append(
                    SyncValidationIssue(
                        "error",
                        "bundle_acquisition_args_invalid",
                        f"DAQ action '{action.name}' sample_rate and samples must be positive",
                    )
                )
                continue
            window = float(samples) / float(sample_rate)
            if window < required:
                issues.append(
                    SyncValidationIssue(
                        "error",
                        "bundle_acquisition_window_short",
                        f"DAQ action '{action.name}' acquisition window {window:g}s is shorter than bundle "
                        f"'{bundle.id}' required {required:g}s",
                    )
                )
        if not found_literal:
            issues.append(
                SyncValidationIssue(
                    "warning",
                    "bundle_acquisition_window_unknown",
                    f"Bundle '{bundle.id}' acquisition window cannot be computed from literal sample_rate/samples",
                )
            )

    def _validate_routes(
        self,
        source_resource: str,
        acquisition_actions: list[ActionStep],
        sync_plan: SyncPlan | None,
        issues: list[SyncValidationIssue],
    ) -> None:
        if sync_plan is None:
            return
        targets_by_resource: dict[str, list[Any]] = {}
        for trigger in sync_plan.triggers:
            if not trigger.source.lower().startswith(f"{source_resource.lower()}.") or "." not in trigger.target:
                continue
            target_resource = trigger.target.split(".", 1)[0]
            targets_by_resource.setdefault(target_resource, []).append(trigger)
        for action in acquisition_actions:
            resource_name = str(action.action).split(".", 1)[0]
            start_trigger = action.kwargs.get("start_trigger", action.kwargs.get("trigger"))
            if start_trigger is None or isinstance(start_trigger, ParameterRef):
                continue
            candidates = targets_by_resource.get(resource_name, [])
            matching = [
                trigger
                for trigger in candidates
                if _normalize_channel(trigger.target.split(".", 1)[1]) == _normalize_channel(start_trigger)
            ]
            if not matching:
                issues.append(
                    SyncValidationIssue(
                        "error",
                        "bundle_trigger_route_mismatch",
                        f"DAQ action '{action.name}' start trigger {start_trigger!r} does not match sync target "
                        f"for resource '{resource_name}'",
                    )
                )
                continue
            edge = action.kwargs.get("edge")
            if isinstance(edge, str) and all(trigger.edge.lower() != edge.lower() for trigger in matching):
                issues.append(
                    SyncValidationIssue(
                        "error",
                        "bundle_trigger_edge_mismatch",
                        f"DAQ action '{action.name}' edge '{edge}' does not match sync trigger edge",
                    )
                )


def _bundle_actions(
    steps: Iterable[Step],
    scan_domains: Mapping[str, tuple[Any, ...]] | None = None,
) -> Iterable[tuple[ActionStep, dict[str, tuple[Any, ...]]]]:
    domains = dict(scan_domains or {})
    for step in steps:
        if isinstance(step, ActionStep) and isinstance(step.action, str) and step.action.endswith(
            ".load_sequence_from_bundle"
        ):
            yield step, dict(domains)
        child_domains = domains
        if isinstance(step, ScanStep):
            child_domains = dict(domains)
            child_domains[step.name] = tuple(step.values)
        body = getattr(step, "body", None)
        if body:
            yield from _bundle_actions(body, child_domains)


def _walk_steps(steps: Iterable[Step]) -> Iterable[Step]:
    for step in steps:
        yield step
        body = getattr(step, "body", None)
        if body:
            yield from _walk_steps(body)


def _method_name(action: ActionStep) -> str:
    if not isinstance(action.action, str) or "." not in action.action:
        return ""
    return action.action.split(".", 1)[1]


def _normalize_channel(value: Any) -> str:
    text = str(value).strip().replace("\\", "/").lower()
    return text.rsplit("/", 1)[-1]


def _dedupe_issues(issues: list[SyncValidationIssue]) -> list[SyncValidationIssue]:
    seen: set[tuple[str, str, str]] = set()
    result: list[SyncValidationIssue] = []
    for issue in issues:
        key = (issue.severity, issue.code, issue.message)
        if key not in seen:
            seen.add(key)
            result.append(issue)
    return result
