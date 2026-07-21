import json
from pathlib import Path

import numpy as np

from qulab.core import DataPoint
from qulab.storage import event_to_jsonable


def test_event_to_jsonable_converts_numpy_and_paths() -> None:
    event = DataPoint(
        point_id="p000001",
        coords={"freq": np.float64(2.87e9)},
        data={"bins": np.array([1, 2, 3]), "path": Path("artifact.txt")},
    )

    payload = event_to_jsonable(event)

    assert payload["coords"]["freq"] == 2.87e9
    assert payload["data"]["bins"] == [1, 2, 3]
    assert payload["data"]["path"] == "artifact.txt"
    json.dumps(payload)
