from qulab.analysis.lineage import input_lineage, source_run_fingerprint, stable_hash


def test_lineage_hashes_are_stable(tmp_path):
    (tmp_path / "data.jsonl").write_text("one\n")
    first = source_run_fingerprint(tmp_path); second = source_run_fingerprint(tmp_path)
    assert first == second and len(first["fingerprint"]) == 64
    assert stable_hash({"b": 2, "a": 1}) == stable_hash({"a": 1, "b": 2})
    assert input_lineage(["raw", "live:key"]) == ["raw:raw", "live:key"]
