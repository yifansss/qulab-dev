"""Offline sequence bundle manifest loading, validation, and resolution.

This module deliberately has no executor, GUI, or hardware dependencies.  It
turns a version-1 manifest into typed objects whose concrete sequence files can
be selected deterministically from point coordinates.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from qulab.paths import resolve_project_path


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")
_COORDINATE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_NUMERIC_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")
_MATCH_MODES = {"exact", "nearest", "id"}


class SequenceBundleError(ValueError):
    """Base class for sequence bundle errors."""


class SequenceBundleManifestError(SequenceBundleError):
    """Raised when a manifest cannot be found or decoded."""


class SequenceBundleValidationError(SequenceBundleError):
    """Raised when a manifest or match policy is structurally invalid."""


class SequenceBundleResolutionError(SequenceBundleError):
    """Raised when point coordinates cannot select one unique entry."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SequenceBundleEntry:
    id: str
    coordinates: Mapping[str, Any]
    sequence_file: Path
    sha256: str
    metadata: Mapping[str, Any] = field(default_factory=dict)
    extra: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result = {
            "id": self.id,
            "coordinates": dict(self.coordinates),
            "sequence_file": str(self.sequence_file),
            "sha256": self.sha256,
            "metadata": _serializable(self.metadata),
        }
        result.update(_serializable(self.extra))
        return result


@dataclass(frozen=True)
class SequenceBundleSelection:
    bundle_id: str
    resource: str
    entry_id: str
    requested_coordinates: Mapping[str, Any]
    entry_coordinates: Mapping[str, Any]
    sequence_file: Path
    sequence_sha256: str
    manifest_path: Path
    manifest_sha256: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "resource": self.resource,
            "entry_id": self.entry_id,
            "requested_coordinates": dict(self.requested_coordinates),
            "entry_coordinates": dict(self.entry_coordinates),
            "sequence_file": str(self.sequence_file),
            "sequence_sha256": self.sequence_sha256,
            "manifest_path": str(self.manifest_path),
            "manifest_sha256": self.manifest_sha256,
            "metadata": _serializable(self.metadata),
        }


@dataclass(frozen=True)
class BundleCoverageIssue:
    code: str
    message: str
    coordinates: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "coordinates": None if self.coordinates is None else dict(self.coordinates),
        }


@dataclass(frozen=True)
class BundleCoverageReport:
    ok: bool
    matched: int
    requested: int
    issues: tuple[BundleCoverageIssue, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "matched": self.matched,
            "requested": self.requested,
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass(frozen=True)
class SequenceBundle:
    schema_version: int
    id: str
    resource: str
    entries: tuple[SequenceBundleEntry, ...]
    manifest_path: Path
    manifest_sha256: str
    coordinates: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    format: str | None = None
    match_mode: str = "exact"
    tolerance: Mapping[str, float] = field(default_factory=dict)
    generator: Mapping[str, Any] | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)

    def resolve(
        self,
        coordinates: Mapping[str, Any] | None = None,
        *,
        entry_id: str | None = None,
        mode: str | None = None,
        tolerance: Mapping[str, float] | None = None,
    ) -> SequenceBundleSelection:
        selected_mode = self.match_mode if mode is None else _validate_mode(mode, self.id)
        requested = dict(coordinates or {})
        if selected_mode == "id":
            if not entry_id:
                raise SequenceBundleResolutionError(
                    "missing_entry_id", f"Bundle '{self.id}' id matching requires an explicit entry_id"
                )
            matches = [entry for entry in self.entries if entry.id == entry_id]
            if not matches:
                raise SequenceBundleResolutionError(
                    "entry_not_found", f"Bundle '{self.id}' has no entry with id '{entry_id}'"
                )
            return self._selection(matches[0], requested)

        required = tuple(self.entries[0].coordinates)
        missing = [name for name in required if name not in requested]
        if missing:
            raise SequenceBundleResolutionError(
                "missing_coordinates",
                f"Bundle '{self.id}' requires coordinates: {', '.join(missing)}",
            )
        for name in required:
            _validate_coordinate_value(requested[name], f"requested coordinate '{name}'")

        if selected_mode == "exact":
            matches = [
                entry
                for entry in self.entries
                if all(_values_equal(requested[name], entry.coordinates[name]) for name in required)
            ]
        else:
            selected_tolerance = dict(self.tolerance if tolerance is None else tolerance)
            numeric_names = [
                name for name in required if _is_number(self.entries[0].coordinates[name])
            ]
            selected_tolerance = _validate_tolerance(
                selected_tolerance, numeric_names, self.id, allowed_names=set(required)
            )
            candidates: list[tuple[float, SequenceBundleEntry]] = []
            for entry in self.entries:
                distance = 0.0
                candidate = True
                for name in required:
                    actual = entry.coordinates[name]
                    wanted = requested[name]
                    if _is_number(actual):
                        if not _is_number(wanted):
                            candidate = False
                            break
                        delta = abs(float(wanted) - float(actual))
                        limit = selected_tolerance[name]
                        if delta > limit:
                            candidate = False
                            break
                        if limit == 0.0:
                            if delta != 0.0:
                                candidate = False
                                break
                        else:
                            distance += (delta / limit) ** 2
                    elif not _values_equal(wanted, actual):
                        candidate = False
                        break
                if candidate:
                    candidates.append((distance, entry))
            if candidates:
                best_distance = min(item[0] for item in candidates)
                matches = [
                    entry
                    for distance, entry in candidates
                    if math.isclose(distance, best_distance, rel_tol=1e-12, abs_tol=1e-15)
                ]
            else:
                matches = []

        if not matches:
            raise SequenceBundleResolutionError(
                "no_match", f"Bundle '{self.id}' has no {selected_mode} match for coordinates {requested!r}"
            )
        if len(matches) != 1:
            ids = ", ".join(entry.id for entry in matches)
            raise SequenceBundleResolutionError(
                "ambiguous_match",
                f"Bundle '{self.id}' has an ambiguous {selected_mode} match for coordinates "
                f"{requested!r}: {ids}",
            )
        return self._selection(matches[0], requested)

    def _selection(
        self, entry: SequenceBundleEntry, requested: Mapping[str, Any]
    ) -> SequenceBundleSelection:
        return SequenceBundleSelection(
            bundle_id=self.id,
            resource=self.resource,
            entry_id=entry.id,
            requested_coordinates=dict(requested),
            entry_coordinates=dict(entry.coordinates),
            sequence_file=entry.sequence_file,
            sequence_sha256=entry.sha256,
            manifest_path=self.manifest_path,
            manifest_sha256=self.manifest_sha256,
            metadata=dict(entry.metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "kind": "sequence_bundle",
            "id": self.id,
            "resource": self.resource,
            "entries": [entry.to_dict() for entry in self.entries],
            "manifest_path": str(self.manifest_path),
            "manifest_sha256": self.manifest_sha256,
            "coordinates": _serializable(self.coordinates),
            "match": {"mode": self.match_mode, "tolerance": dict(self.tolerance)},
        }
        if self.format is not None:
            result["format"] = self.format
        if self.generator is not None:
            result["generator"] = _serializable(self.generator)
        result.update(_serializable(self.extra))
        return result


def load_sequence_bundle(
    manifest: str | Path,
    *,
    declared_id: str | None = None,
    declared_resource: str | None = None,
    match: Mapping[str, Any] | None = None,
    validate_files: bool = True,
) -> SequenceBundle:
    """Load and fully validate a version-1 sequence bundle manifest."""

    manifest_path = _resolve_manifest_path(manifest)
    if not manifest_path.is_file():
        label = declared_id or "unknown"
        raise SequenceBundleManifestError(
            f"Sequence bundle '{label}' manifest not found: {manifest_path}"
        )
    try:
        raw_bytes = manifest_path.read_bytes()
    except OSError as exc:
        raise SequenceBundleManifestError(f"Cannot read sequence bundle manifest: {manifest_path}: {exc}") from exc
    try:
        raw = yaml.safe_load(raw_bytes)
    except yaml.YAMLError as exc:
        raise SequenceBundleManifestError(f"Invalid YAML in sequence bundle manifest {manifest_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise SequenceBundleValidationError(f"Sequence bundle manifest must be a mapping: {manifest_path}")

    schema_version = raw.get("schema_version", 1)
    if isinstance(schema_version, bool) or not isinstance(schema_version, int) or schema_version != 1:
        raise SequenceBundleValidationError(
            f"Unsupported sequence bundle schema_version {schema_version!r} in {manifest_path}; expected 1"
        )
    if raw.get("kind") != "sequence_bundle":
        raise SequenceBundleValidationError(
            f"Sequence bundle manifest {manifest_path} must declare kind: sequence_bundle"
        )
    bundle_id = _required_identifier(raw.get("id"), "bundle id")
    resource = _required_identifier(raw.get("resource"), f"bundle '{bundle_id}' resource")
    if declared_id is not None and declared_id != bundle_id:
        raise SequenceBundleValidationError(
            f"Sequence bundle config id '{declared_id}' does not match manifest id '{bundle_id}'"
        )
    if declared_resource is not None and declared_resource != resource:
        raise SequenceBundleValidationError(
            f"Sequence bundle '{bundle_id}' config resource '{declared_resource}' does not match "
            f"manifest resource '{resource}'"
        )

    coordinate_specs = _parse_coordinate_specs(raw.get("coordinates", {}), bundle_id)
    raw_entries = raw.get("entries")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise SequenceBundleValidationError(f"Sequence bundle '{bundle_id}' entries must be a non-empty list")
    entries = tuple(
        _parse_entry(item, index, bundle_id, manifest_path, validate_files)
        for index, item in enumerate(raw_entries)
    )
    _validate_entries(entries, coordinate_specs, bundle_id)

    match_config = {} if match is None else _require_mapping(match, f"bundle '{bundle_id}' match")
    mode = _validate_mode(match_config.get("mode", "exact"), bundle_id)
    tolerance_raw = match_config.get("tolerance", {})
    tolerance_mapping = _require_mapping(tolerance_raw, f"bundle '{bundle_id}' match.tolerance")
    numeric_names = [name for name, value in entries[0].coordinates.items() if _is_number(value)]
    tolerance = (
        _validate_tolerance(tolerance_mapping, numeric_names, bundle_id, allowed_names=set(entries[0].coordinates))
        if mode == "nearest"
        else _validate_optional_tolerance(tolerance_mapping, bundle_id, set(entries[0].coordinates))
    )
    known = {"schema_version", "kind", "id", "resource", "format", "coordinates", "entries", "generator"}
    return SequenceBundle(
        schema_version=1,
        id=bundle_id,
        resource=resource,
        entries=entries,
        manifest_path=manifest_path,
        manifest_sha256=hashlib.sha256(raw_bytes).hexdigest(),
        coordinates=coordinate_specs,
        format=None if raw.get("format") is None else str(raw["format"]),
        match_mode=mode,
        tolerance=tolerance,
        generator=_optional_mapping(raw.get("generator"), f"bundle '{bundle_id}' generator"),
        extra={key: value for key, value in raw.items() if key not in known},
    )


def validate_bundle_coverage(
    bundle: SequenceBundle,
    points: Iterable[Mapping[str, Any]],
) -> BundleCoverageReport:
    """Resolve all supplied points and aggregate misses without hardware I/O."""

    requested = 0
    matched = 0
    issues: list[BundleCoverageIssue] = []
    for point in points:
        requested += 1
        coordinates = dict(point)
        try:
            bundle.resolve(coordinates)
        except SequenceBundleResolutionError as exc:
            issues.append(BundleCoverageIssue(exc.code, str(exc), coordinates))
        except (SequenceBundleError, TypeError, ValueError) as exc:
            issues.append(BundleCoverageIssue("invalid_coordinates", str(exc), coordinates))
        else:
            matched += 1
    return BundleCoverageReport(not issues, matched, requested, tuple(issues))


def _resolve_manifest_path(manifest: str | Path) -> Path:
    text = str(manifest).strip()
    if not text:
        raise SequenceBundleManifestError("Sequence bundle manifest path is empty")
    normalized = text.replace("\\", os.sep) if os.sep == "/" else text
    resolved = resolve_project_path(normalized)
    return resolved if resolved is not None else Path(normalized).expanduser()


def _parse_coordinate_specs(raw: Any, bundle_id: str) -> dict[str, dict[str, Any]]:
    specs = _require_mapping(raw, f"bundle '{bundle_id}' coordinates")
    result: dict[str, dict[str, Any]] = {}
    for name, spec_raw in specs.items():
        if not isinstance(name, str) or not _COORDINATE_RE.fullmatch(name):
            raise SequenceBundleValidationError(
                f"Bundle '{bundle_id}' coordinate name {name!r} is not a stable identifier"
            )
        spec = _require_mapping(spec_raw, f"bundle '{bundle_id}' coordinate '{name}'")
        parsed = dict(spec)
        if "unit" in parsed and (not isinstance(parsed["unit"], str) or not parsed["unit"].strip()):
            raise SequenceBundleValidationError(
                f"Bundle '{bundle_id}' coordinate '{name}' unit must be a non-empty string"
            )
        if "values" in parsed:
            if not isinstance(parsed["values"], list) or not parsed["values"]:
                raise SequenceBundleValidationError(
                    f"Bundle '{bundle_id}' coordinate '{name}' values must be a non-empty list"
                )
            parsed["values"] = [_coerce_coordinate_value(value) for value in parsed["values"]]
            for value in parsed["values"]:
                _validate_coordinate_value(value, f"bundle '{bundle_id}' coordinate '{name}' value")
        result[name] = parsed
    return result


def _parse_entry(
    raw: Any,
    index: int,
    bundle_id: str,
    manifest_path: Path,
    validate_files: bool,
) -> SequenceBundleEntry:
    location = f"bundle '{bundle_id}' entry[{index}]"
    entry = _require_mapping(raw, location)
    entry_id = _required_identifier(entry.get("id"), f"{location} id")
    coordinates_raw = _require_mapping(entry.get("coordinates"), f"{location} coordinates")
    if not coordinates_raw:
        raise SequenceBundleValidationError(f"{location} coordinates must not be empty")
    coordinates: dict[str, Any] = {}
    for name, raw_value in coordinates_raw.items():
        if not isinstance(name, str) or not _COORDINATE_RE.fullmatch(name):
            raise SequenceBundleValidationError(f"{location} coordinate name {name!r} is invalid")
        value = _coerce_coordinate_value(raw_value)
        _validate_coordinate_value(value, f"{location} coordinate '{name}'")
        coordinates[name] = value

    sequence_value = entry.get("sequence_file")
    if not isinstance(sequence_value, (str, Path)) or not str(sequence_value).strip():
        raise SequenceBundleValidationError(f"{location} sequence_file is required")
    text = str(sequence_value).strip()
    normalized = text.replace("\\", os.sep) if os.sep == "/" else text
    path = Path(normalized).expanduser()
    if not path.is_absolute():
        path = (manifest_path.parent / path).resolve()
    elif path.exists():
        path = path.resolve()
    if validate_files and not path.is_file():
        raise SequenceBundleManifestError(
            f"Sequence bundle '{bundle_id}' entry '{entry_id}' sequence file not found: {path}"
        )
    actual_sha256 = _sha256(path) if path.is_file() else ""
    declared_sha256 = entry.get("sha256")
    if declared_sha256 is not None:
        if not isinstance(declared_sha256, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", declared_sha256):
            raise SequenceBundleValidationError(f"{location} sha256 must contain 64 hexadecimal characters")
        declared_sha256 = declared_sha256.lower()
        if actual_sha256 and declared_sha256 != actual_sha256:
            raise SequenceBundleValidationError(
                f"Sequence bundle '{bundle_id}' entry '{entry_id}' sha256 mismatch for {path}: "
                f"declared {declared_sha256}, actual {actual_sha256}"
            )
    metadata = _require_mapping(entry.get("metadata", {}), f"{location} metadata")
    metadata = dict(metadata)
    _validate_metadata(metadata, location)
    known = {"id", "coordinates", "sequence_file", "sha256", "metadata"}
    return SequenceBundleEntry(
        id=entry_id,
        coordinates=coordinates,
        sequence_file=path,
        sha256=actual_sha256 or (declared_sha256 or ""),
        metadata=metadata,
        extra={key: value for key, value in entry.items() if key not in known},
    )


def _validate_entries(
    entries: tuple[SequenceBundleEntry, ...],
    specs: Mapping[str, Mapping[str, Any]],
    bundle_id: str,
) -> None:
    ids: set[str] = set()
    tuples: dict[tuple[Any, ...], str] = {}
    expected_keys = tuple(entries[0].coordinates)
    expected_set = set(expected_keys)
    if specs and set(specs) != expected_set:
        raise SequenceBundleValidationError(
            f"Bundle '{bundle_id}' declared coordinate keys {sorted(specs)} do not match entry keys "
            f"{sorted(expected_set)}"
        )
    for entry in entries:
        if entry.id in ids:
            raise SequenceBundleValidationError(
                f"Sequence bundle '{bundle_id}' has duplicate entry id '{entry.id}'"
            )
        ids.add(entry.id)
        if set(entry.coordinates) != expected_set:
            raise SequenceBundleValidationError(
                f"Sequence bundle '{bundle_id}' entry '{entry.id}' coordinate keys "
                f"{sorted(entry.coordinates)} do not match {sorted(expected_set)}"
            )
        for name in expected_keys:
            reference = entries[0].coordinates[name]
            value = entry.coordinates[name]
            same_kind = (_is_number(reference) and _is_number(value)) or type(reference) is type(value)
            if not same_kind:
                raise SequenceBundleValidationError(
                    f"Sequence bundle '{bundle_id}' entry '{entry.id}' coordinate '{name}' type "
                    f"{type(value).__name__} does not match {type(reference).__name__}"
                )
        for name, value in entry.coordinates.items():
            allowed = specs.get(name, {}).get("values")
            if allowed is not None and not any(_values_equal(value, item) for item in allowed):
                raise SequenceBundleValidationError(
                    f"Sequence bundle '{bundle_id}' entry '{entry.id}' coordinate '{name}' value "
                    f"{value!r} is not declared in coordinates.{name}.values"
                )
        coordinate_tuple = tuple(_canonical_value(entry.coordinates[name]) for name in expected_keys)
        if coordinate_tuple in tuples:
            raise SequenceBundleValidationError(
                f"Sequence bundle '{bundle_id}' entries '{tuples[coordinate_tuple]}' and '{entry.id}' "
                "have duplicate coordinate tuples"
            )
        tuples[coordinate_tuple] = entry.id


def _validate_metadata(metadata: Mapping[str, Any], location: str) -> None:
    if "duration_s" in metadata:
        duration = _coerce_coordinate_value(metadata["duration_s"])
        if not _is_number(duration) or float(duration) <= 0 or not math.isfinite(float(duration)):
            raise SequenceBundleValidationError(f"{location} metadata.duration_s must be finite and positive")
        if isinstance(metadata, dict):
            metadata["duration_s"] = duration
    for key in ("trigger_channels", "output_channels"):
        if key in metadata:
            channels = metadata[key]
            if not isinstance(channels, list) or not channels or any(
                not isinstance(channel, str) or not channel.strip() for channel in channels
            ):
                raise SequenceBundleValidationError(
                    f"{location} metadata.{key} must be a non-empty list of non-empty strings"
                )


def _validate_mode(mode: Any, bundle_id: str) -> str:
    if not isinstance(mode, str) or mode not in _MATCH_MODES:
        raise SequenceBundleValidationError(
            f"Sequence bundle '{bundle_id}' match.mode must be one of exact, nearest, id; got {mode!r}"
        )
    return mode


def _validate_tolerance(
    raw: Mapping[str, Any],
    numeric_names: Iterable[str],
    bundle_id: str,
    *,
    allowed_names: set[str],
) -> dict[str, float]:
    result = _validate_optional_tolerance(raw, bundle_id, allowed_names)
    missing = [name for name in numeric_names if name not in result]
    if missing:
        raise SequenceBundleValidationError(
            f"Sequence bundle '{bundle_id}' nearest matching requires explicit tolerance for: "
            f"{', '.join(missing)}"
        )
    return result


def _validate_optional_tolerance(
    raw: Mapping[str, Any], bundle_id: str, allowed_names: set[str]
) -> dict[str, float]:
    result: dict[str, float] = {}
    for name, value in raw.items():
        if name not in allowed_names:
            raise SequenceBundleValidationError(
                f"Sequence bundle '{bundle_id}' tolerance refers to unknown coordinate '{name}'"
            )
        if not _is_number(value):
            raise SequenceBundleValidationError(
                f"Sequence bundle '{bundle_id}' tolerance for '{name}' must be numeric"
            )
        number = float(value)
        if number < 0 or not math.isfinite(number):
            raise SequenceBundleValidationError(
                f"Sequence bundle '{bundle_id}' tolerance for '{name}' must be finite and non-negative"
            )
        result[str(name)] = number
    return result


def _validate_coordinate_value(value: Any, location: str) -> None:
    if isinstance(value, bool):
        raise SequenceBundleValidationError(f"{location} must not be boolean")
    if _is_number(value):
        try:
            finite = math.isfinite(float(value))
        except (OverflowError, ValueError):
            finite = False
        if not finite:
            raise SequenceBundleValidationError(f"{location} must be finite")
        return
    if value is None or isinstance(value, (dict, list, tuple, set)):
        raise SequenceBundleValidationError(f"{location} must be a scalar coordinate value")


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _values_equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if _is_number(left) and _is_number(right):
        return left == right
    return type(left) is type(right) and left == right


def _canonical_value(value: Any) -> tuple[str, Any]:
    if _is_number(value):
        return ("number", float(value))
    return (type(value).__name__, value)


def _coerce_coordinate_value(value: Any) -> Any:
    if isinstance(value, str) and _NUMERIC_RE.fullmatch(value.strip()):
        text = value.strip()
        return float(text) if any(character in text for character in ".eE") else int(text)
    return value


def _required_identifier(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip() or not _IDENTIFIER_RE.fullmatch(value.strip()):
        raise SequenceBundleValidationError(f"{location} must be a non-empty stable identifier")
    return value.strip()


def _require_mapping(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SequenceBundleValidationError(f"{location} must be a mapping")
    return dict(value)


def _optional_mapping(value: Any, location: str) -> dict[str, Any] | None:
    if value is None:
        return None
    return _require_mapping(value, location)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise SequenceBundleManifestError(f"Cannot hash sequence file {path}: {exc}") from exc
    return digest.hexdigest()


def _serializable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _serializable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serializable(item) for item in value]
    return value
