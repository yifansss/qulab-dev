from pathlib import Path

from qulab.sequence_bundles import load_sequence_bundle, validate_bundle_coverage


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "configs" / "sequences" / "examples" / "rabi_tau_bundle" / "manifest.yaml"


def test_coverage_aggregates_multiple_misses_and_counts_duplicate_requests() -> None:
    bundle = load_sequence_bundle(MANIFEST)
    report = validate_bundle_coverage(
        bundle,
        [{"tau_s": 20e-9}, {"tau_s": 20e-9}, {"tau_s": 21e-9}, {"wrong": 1}, {"tau_s": 90e-9}],
    )

    assert report.ok is False
    assert report.requested == 5
    assert report.matched == 2
    assert len(report.issues) == 3
    assert [issue.code for issue in report.issues] == ["no_match", "missing_coordinates", "no_match"]
    assert report.issues[0].coordinates == {"tau_s": 21e-9}


def test_coverage_success_serializes() -> None:
    bundle = load_sequence_bundle(
        MANIFEST,
        match={"mode": "nearest", "tolerance": {"tau_s": 1e-9}},
    )
    report = validate_bundle_coverage(bundle, [{"tau_s": 20.5e-9}, {"tau_s": 60e-9}])

    assert report.ok is True
    assert report.matched == report.requested == 2
    assert report.to_dict()["issues"] == []
