import json

import pytest

from qulab.analysis import AnalysisResultStore
from qulab.core import DerivedData


def test_result_store_commits_atomically_and_history_is_append_only(tmp_path):
    store = AnalysisResultStore(tmp_path, "result_1", backends=["csv"], metadata={"input_lineage": ["raw:x"]})
    store.open(); store.append(DerivedData(point_id="p1", coords={"x": 1}, data={"y": 2},
                                           source_module="m", module_version="1", input_keys=["x"], run_mode="post"))
    path = store.commit()
    assert path == tmp_path / "analysis" / "result_1"
    assert not any(item.name.startswith(".tmp_") for item in (tmp_path / "analysis").iterdir())
    assert json.loads((path / "metadata.json").read_text())["status"] == "completed"
    events = [json.loads(line)["event"] for line in (tmp_path / "analysis" / "history.jsonl").read_text().splitlines()]
    assert events == ["started", "completed"]
    with pytest.raises(FileExistsError): AnalysisResultStore(tmp_path, "result_1").open()


def test_failed_store_does_not_expose_final_group(tmp_path):
    store = AnalysisResultStore(tmp_path, "failed")
    store.open(); store.fail(RuntimeError("boom"))
    assert not (tmp_path / "analysis" / "failed").exists()
    assert json.loads((tmp_path / "analysis" / "history.jsonl").read_text().splitlines()[-1])["event"] == "failed"
