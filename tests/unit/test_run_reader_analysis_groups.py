from qulab.analysis import AnalysisResultStore
from qulab.core import DerivedData
from qulab.storage import DatasetModel, RunReader


def test_group_discovery_and_read(tmp_path):
    store = AnalysisResultStore(tmp_path, "v1", backends=["csv"], metadata={"input_lineage": ["raw:x"]})
    store.open(); store.append(DerivedData(point_id="p1", coords={"x": 1}, data={"out": 2}, source_module="m",
                                           module_version="1", input_keys=["x"], run_mode="post")); store.commit()
    reader = RunReader(tmp_path)
    assert reader.list_data_groups() == ["raw", "analysis:v1"]
    assert reader.list_data_keys(group="analysis:v1") == ["out"]
    data = reader.get_data_var("out", group="analysis:v1")
    assert data.values.tolist() == [2.0]
    info = DatasetModel(reader, group="analysis:v1").describe_data_key("out")
    assert info.source_kind == "derived" and info.source_module == "m"
