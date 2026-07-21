"""Generic plan-configured ASG JSON template sweep provider."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ..errors import SequenceGenerationError, SequenceGenerationIssue
from ..models import GeneratedSequencePoint, SequenceFamilySpec, SequencePlanValidationResult, SequenceSweepPlan
from .asg_model import AsgSequence
from .asg_transforms import preview_from_model, resolve_targets, transform_sequence


class AsgTemplateSweepProvider:
    def __init__(self) -> None:
        self.plan: SequenceSweepPlan | None = None

    def describe(self) -> SequenceFamilySpec:
        return SequenceFamilySpec("asg_template", "1", "Generic ASG template sweep", "pycontrol_asg_json", (),
                                  supports_preview=True, description="Structured pulse target transforms over ASG JSON.",
                                  dynamic_parameters=True)

    def configure_plan(self, plan: SequenceSweepPlan) -> None:
        self.plan = plan

    def validate_plan(self, plan: SequenceSweepPlan) -> SequencePlanValidationResult:
        try:
            if plan.template is None:
                raise SequenceGenerationError("sequence_template_invalid", "ASG template provider requires template")
            base = AsgSequence.from_path(plan.template)
            resolve_targets(base, plan)
            parameters = {name: (value.value if value.value is not None else value.start if value.start is not None else value.values[0] if value.values else 0.0)
                          for name, value in plan.parameters.items()}
            transform_sequence(base, plan, parameters)
        except SequenceGenerationError as exc:
            return SequencePlanValidationResult((exc.as_issue(),))
        return SequencePlanValidationResult()

    def _generate_model(self, parameters: Mapping[str, Any], template: Path | None) -> AsgSequence:
        if self.plan is None or template is None:
            raise SequenceGenerationError("sequence_template_invalid", "Provider was not configured with a template plan")
        return transform_sequence(AsgSequence.from_path(template), self.plan, parameters)

    def generate_point(self, parameters: Mapping[str, Any], *, template: Path | None) -> GeneratedSequencePoint:
        model = self._generate_model(parameters, template)
        views = model.views(); options = self.plan.options if self.plan else {}
        metadata = {"duration_s": max((item.block_end_s for item in views), default=0.0),
                    "output_channels": sorted({item.channel for item in views}), "parameters": dict(parameters),
                    "targets": dict(self.plan.targets if self.plan else {}), "template_sha256": model.template_sha256,
                    "provider_version": "1"}
        if isinstance(options.get("trigger_channels"), (list, tuple)):
            metadata["trigger_channels"] = list(options["trigger_channels"])
        if options.get("readout_window_s") is not None:
            metadata["readout_window_s"] = float(options["readout_window_s"])
        return GeneratedSequencePoint(model.to_bytes(), ".json", metadata)

    def preview_point(self, parameters: Mapping[str, Any], *, template: Path | None):
        model = self._generate_model(parameters, template)
        return preview_from_model(model, resolve_targets(model, self.plan))


PROVIDER = AsgTemplateSweepProvider()
def get_provider(): return AsgTemplateSweepProvider()
