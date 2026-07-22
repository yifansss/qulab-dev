import hashlib

from qulab.analysis.recompute import recompute_run
from qulab.config import run_dry_config
from test_post_run_recompute import source_config


def hashes(path):
    return {str(item.relative_to(path)): hashlib.sha256(item.read_bytes()).hexdigest() for item in path.rglob("*")
            if item.is_file() and "analysis" not in item.parts}


def test_recompute_only_writes_analysis_tree(tmp_path):
    source = run_dry_config(source_config(), tmp_path / "runs").run_path
    before = hashes(source); recompute_run(source, ["scale_preview"], result_id="immutable"); after = hashes(source)
    assert before == after
