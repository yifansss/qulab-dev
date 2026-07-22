"""Deterministic generic transforms used by the Live View showcase."""
from qulab.analysis import ComputeArgumentSpec, ComputePoint, ComputeResult


class _BaseTransform:
    input_keys = ("source_value",)
    @staticmethod
    def describe_arguments():
        return (ComputeArgumentSpec("factor", "number", default=1.0),)
    def setup(self, config, run_context): self.factor = float(config["factor"])
    def process_point(self, point: ComputePoint) -> ComputeResult:
        return ComputeResult({self.output_keys[0]: point.data["source_value"] * self.factor})
    def close(self): pass


class SavedScale(_BaseTransform):
    name = "showcase_saved_scale"; version = "1"; output_keys = ("saved_scale",)


class LiveOnlyScale(_BaseTransform):
    name = "showcase_live_only_scale"; version = "1"; output_keys = ("live_only_scale",)


class WaitingScale(_BaseTransform):
    name = "showcase_waiting_scale"; version = "1"; input_keys = ("never_emitted",); output_keys = ("waiting_preview",)
    def process_point(self, point: ComputePoint) -> ComputeResult:
        return ComputeResult({"waiting_preview": point.data["never_emitted"] * self.factor})
