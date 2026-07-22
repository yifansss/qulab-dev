import json

import pytest

from qulab.analysis import ComputeArgumentSpec, ComputePoint, ComputeResult


def test_public_models_are_json_safe():
    point = ComputePoint("p1", {"x": 1}, {"raw": [1, 2]}, {}, "now")
    result = ComputeResult({"value": 2}, units={"value": "V"})
    json.dumps(point.to_dict())
    json.dumps(result.to_dict())
    json.dumps(ComputeArgumentSpec("scale", "number", default=1).to_dict())


def test_model_rejects_runtime_object():
    with pytest.raises(TypeError):
        ComputeResult({"bad": object()}).to_dict()
