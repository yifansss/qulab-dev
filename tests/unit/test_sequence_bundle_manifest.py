from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml

from qulab.sequence_bundles import (
    SequenceBundleManifestError,
    SequenceBundleValidationError,
    load_sequence_bundle,
)


ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "configs" / "sequences" / "examples" / "rabi_tau_bundle" / "manifest.yaml"


def _write_bundle(tmp_path: Path, entries: list[dict], coordinates: dict | None = None) -> Path:
    sequence_dir = tmp_path / "sequences"
    sequence_dir.mkdir(exist_ok=True)
    for entry in entries:
        path = sequence_dir / Path(entry["sequence_file"]).name
        if not path.exists():
            path.write_text('[{"channel_name": "Channel 1", "pulses": []}]', encoding="utf-8")
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "kind": "sequence_bundle",
                "id": "test_bundle",
                "resource": "asg",
                "coordinates": coordinates or {"tau_s": {"unit": "s", "values": [1.0, 2.0]}},
                "entries": entries,
                "generator": {"module": "example.generator", "custom": "kept"},
                "custom_manifest_field": {"owner": "lab"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return manifest


def _entries() -> list[dict]:
    return [
        {
            "id": "tau_1",
            "coordinates": {"tau_s": 1.0},
            "sequence_file": "sequences/tau_1.json",
            "metadata": {
                "duration_s": 8e-6,
                "trigger_channels": ["ch6"],
                "output_channels": ["ch1", "ch6"],
                "custom": {"label": "first"},
            },
            "custom_entry_field": "kept",
        },
        {"id": "tau_2", "coordinates": {"tau_s": 2.0}, "sequence_file": "sequences/tau_2.json"},
    ]


def test_example_manifest_loads_manifest_relative_files_and_raw_hashes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT.parent)
    bundle = load_sequence_bundle("configs/sequences/examples/rabi_tau_bundle/manifest.yaml")

    assert bundle.id == "rabi_tau"
    assert len(bundle.entries) == 3
    assert bundle.manifest_sha256 == hashlib.sha256(EXAMPLE.read_bytes()).hexdigest()
    for entry in bundle.entries:
        assert entry.sequence_file.parent == EXAMPLE.parent / "sequences"
        assert entry.sha256 == hashlib.sha256(entry.sequence_file.read_bytes()).hexdigest()


def test_optional_and_unknown_metadata_are_preserved_and_serializable(tmp_path: Path) -> None:
    bundle = load_sequence_bundle(_write_bundle(tmp_path, _entries()))
    serialized = bundle.to_dict()

    assert bundle.generator == {"module": "example.generator", "custom": "kept"}
    assert bundle.extra["custom_manifest_field"] == {"owner": "lab"}
    assert bundle.entries[0].metadata["custom"] == {"label": "first"}
    assert bundle.entries[0].extra["custom_entry_field"] == "kept"
    assert isinstance(serialized["manifest_path"], str)
    assert isinstance(serialized["entries"][0]["sequence_file"], str)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda entries: entries.append(dict(entries[0])), "duplicate entry id"),
        (
            lambda entries: entries.append(
                {"id": "another", "coordinates": {"tau_s": 1.0}, "sequence_file": "sequences/another.json"}
            ),
            "duplicate coordinate tuples",
        ),
        (
            lambda entries: entries.__setitem__(
                1,
                {
                    "id": "tau_2",
                    "coordinates": {"other": 2.0},
                    "sequence_file": "sequences/tau_2.json",
                },
            ),
            "coordinate keys",
        ),
    ],
)
def test_structural_entry_errors_are_clear(tmp_path: Path, mutate, message: str) -> None:
    entries = _entries()
    mutate(entries)
    manifest = _write_bundle(tmp_path, entries, coordinates={})

    with pytest.raises(SequenceBundleValidationError, match=message):
        load_sequence_bundle(manifest)


def test_missing_sequence_names_bundle_entry_and_resolved_path(tmp_path: Path) -> None:
    manifest = _write_bundle(tmp_path, _entries())
    missing = tmp_path / "sequences" / "tau_2.json"
    missing.unlink()

    with pytest.raises(SequenceBundleManifestError) as exc_info:
        load_sequence_bundle(manifest)

    message = str(exc_info.value)
    assert "test_bundle" in message
    assert "tau_2" in message
    assert str(missing) in message


def test_declared_sha256_mismatch_fails_closed(tmp_path: Path) -> None:
    entries = _entries()
    entries[0]["sha256"] = "0" * 64

    with pytest.raises(SequenceBundleValidationError, match="sha256 mismatch"):
        load_sequence_bundle(_write_bundle(tmp_path, entries))


def test_bool_nan_duration_and_bad_channel_metadata_are_rejected(tmp_path: Path) -> None:
    entries = _entries()
    entries[0]["coordinates"]["tau_s"] = True
    with pytest.raises(SequenceBundleValidationError, match="must not be boolean"):
        load_sequence_bundle(_write_bundle(tmp_path, entries, coordinates={}))

    entries = _entries()
    entries[0]["metadata"]["duration_s"] = float("nan")
    with pytest.raises(SequenceBundleValidationError, match="duration_s"):
        load_sequence_bundle(_write_bundle(tmp_path, entries))

    entries = _entries()
    entries[0]["metadata"]["trigger_channels"] = [""]
    with pytest.raises(SequenceBundleValidationError, match="trigger_channels"):
        load_sequence_bundle(_write_bundle(tmp_path, entries))


def test_windows_style_relative_manifest_path_is_supported() -> None:
    bundle = load_sequence_bundle(r"configs\sequences\examples\rabi_tau_bundle\manifest.yaml")

    assert bundle.id == "rabi_tau"
