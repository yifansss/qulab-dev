"""Generic scalar scaling example; this is not an experiment formula."""

from qulab.analysis import ComputeArgumentSpec, ComputePoint, ComputeResult


class PassthroughScale:
    name = "passthrough_scale"
    version = "1"
    input_keys = ("source_value",)
    output_keys = ("scaled_value",)

    @staticmethod
    def describe_arguments() -> tuple[ComputeArgumentSpec, ...]:
        return (ComputeArgumentSpec("scale", "number", default=1.0),)

    def setup(self, config, run_context) -> None:
        self.scale = float(config["scale"])

    def process_point(self, point: ComputePoint) -> ComputeResult:
        return ComputeResult({"scaled_value": point.data["source_value"] * self.scale})

    def close(self) -> None:
        pass
