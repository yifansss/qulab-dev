from pathlib import Path

import pytest

from qulab.sequence_bundles import (
    SequenceBundleResolutionError,
    SequenceBundleValidationError,
    load_sequence_bundle,
)


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "configs" / "sequences" / "examples" / "rabi_tau_bundle" / "manifest.yaml"


def test_exact_resolves_one_entry_and_reports_no_match() -> None:
    bundle = load_sequence_bundle(MANIFEST)

    selection = bundle.resolve({"tau_s": 40e-9})
    assert selection.entry_id == "tau_40ns"
    assert selection.requested_coordinates == {"tau_s": 40e-9}
    assert selection.sequence_sha256 == bundle.entries[1].sha256

    with pytest.raises(SequenceBundleResolutionError, match="no exact match") as exc_info:
        bundle.resolve({"tau_s": 41e-9})
    assert exc_info.value.code == "no_match"


def test_nearest_resolves_within_tolerance_and_rejects_outside() -> None:
    bundle = load_sequence_bundle(
        MANIFEST,
        match={"mode": "nearest", "tolerance": {"tau_s": 2e-9}},
    )

    assert bundle.resolve({"tau_s": 41e-9}).entry_id == "tau_40ns"
    with pytest.raises(SequenceBundleResolutionError, match="no nearest match"):
        bundle.resolve({"tau_s": 50e-9})


def test_nearest_tie_is_ambiguous() -> None:
    bundle = load_sequence_bundle(
        MANIFEST,
        match={"mode": "nearest", "tolerance": {"tau_s": 11e-9}},
    )

    with pytest.raises(SequenceBundleResolutionError, match="ambiguous") as exc_info:
        bundle.resolve({"tau_s": 50e-9})
    assert exc_info.value.code == "ambiguous_match"


@pytest.mark.parametrize("tolerance", [{}, {"tau_s": -1.0}, {"tau_s": float("inf")}])
def test_nearest_requires_non_negative_finite_tolerance(tolerance: dict) -> None:
    with pytest.raises(SequenceBundleValidationError, match="tolerance"):
        load_sequence_bundle(MANIFEST, match={"mode": "nearest", "tolerance": tolerance})


def test_id_matching_requires_and_resolves_explicit_entry_id() -> None:
    bundle = load_sequence_bundle(MANIFEST, match={"mode": "id"})

    assert bundle.resolve(entry_id="tau_60ns").entry_id == "tau_60ns"
    with pytest.raises(SequenceBundleResolutionError, match="explicit entry_id"):
        bundle.resolve()
    with pytest.raises(SequenceBundleResolutionError, match="does_not_exist"):
        bundle.resolve(entry_id="does_not_exist")


def test_missing_required_coordinate_is_not_guessed() -> None:
    bundle = load_sequence_bundle(MANIFEST)

    with pytest.raises(SequenceBundleResolutionError, match="requires coordinates"):
        bundle.resolve({"entry": "tau_20ns"})
