"""Immutable view state for the guided Sequence Sweep Qt page."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from .sequence_authoring import AuthoringStepStatus, LocatedSequenceIssue, NormalizedPreview, SequenceAuthoringModel, SequenceParameterField
from .sequence_sweep_model import SequencePlanViewModel

@dataclass(frozen=True)
class GuidedPlanSummary:
    id: str
    resource: str
    mode: str
    provider: str
    axes: tuple[str, ...]
    point_count: int
    state: str
    plan_hash: str | None

@dataclass(frozen=True)
class GuidedSequenceViewState:
    plans: tuple[GuidedPlanSummary, ...]
    selected_plan: str | None
    mode: str | None
    steps: tuple[AuthoringStepStatus, ...]
    parameter_fields: tuple[SequenceParameterField, ...]
    point_count: int | None
    first_coordinates: dict[str, Any]
    last_coordinates: dict[str, Any]
    issues: tuple[LocatedSequenceIssue, ...]
    prepared_state: str
    plan_hash: str | None
    revision: str | None
    previews: tuple[NormalizedPreview, NormalizedPreview, NormalizedPreview] | None = None

class SequenceAuthoringPresenter:
    def __init__(self, model: SequenceAuthoringModel) -> None: self.model = model

    def state(self, selected_plan: str | None = None, *, include_previews: bool = False,
              current_index: int | None = None) -> GuidedSequenceViewState:
        plans = tuple(self._summary(item) for item in self.model.sweep.list_plans())
        selected = selected_plan if any(item.id == selected_plan for item in plans) else (plans[0].id if plans else None)
        if selected is None:
            return GuidedSequenceViewState(plans, None, None, (), (), None, {}, {}, (), "empty", None, None)
        plan = next(item for item in plans if item.id == selected)
        try:
            estimate = self.model.sweep.estimate(selected)
            first, last, count = dict(estimate.first), dict(estimate.last), estimate.point_count
        except Exception:
            first, last, count = {}, {}, plan.point_count
        previews = None
        if include_previews:
            try: previews = self.model.normalized_previews(selected, current_index)
            except Exception: previews = None
        try: fields = self.model.parameter_fields(selected)
        except Exception: fields = ()
        return GuidedSequenceViewState(plans, selected, self.model.mode(selected), self.model.ordered_status(selected), fields,
                                       count, first, last, self.model.located_issues(selected), plan.state, plan.plan_hash,
                                       self.model.revision(selected), previews)

    def _summary(self, plan: SequencePlanViewModel) -> GuidedPlanSummary:
        return GuidedPlanSummary(plan.id, plan.resource, self.model.mode(plan.id), plan.provider,
                                 tuple(item.name for item in plan.parameters if item.mode != "fixed"),
                                 plan.point_count, plan.state, plan.plan_hash)
