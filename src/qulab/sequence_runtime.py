"""Runtime bridge from workflow point coordinates to concrete sequence files."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

from qulab.core.context import ExperimentContext
from qulab.core.events import EventBus, SequenceSelected
from qulab.sequence_bundles import SequenceBundleResolutionError


class SequenceBundleRuntimeError(RuntimeError):
    """Raised when a bundle workflow action cannot be executed safely."""


def load_sequence_from_bundle(
    context: ExperimentContext,
    event_bus: EventBus,
    *,
    resource_name: str,
    bundle: str,
    coordinates: Mapping[str, Any] | None = None,
    entry_id: str | None = None,
    mode: str | None = None,
    tolerance: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Resolve, verify, load, and emit provenance for one workflow point."""

    requested = dict(coordinates or {})
    bundle_id = bundle
    if bundle_id not in context.sequence_bundles:
        raise SequenceBundleRuntimeError(
            f"Resource '{resource_name}' requested unknown sequence bundle '{bundle_id}' "
            f"for coordinates {requested!r}"
        )
    bundle_model = context.sequence_bundles[bundle_id]
    if bundle_model.resource != resource_name:
        raise SequenceBundleRuntimeError(
            f"Resource '{resource_name}' cannot load sequence bundle '{bundle_id}' declared for "
            f"resource '{bundle_model.resource}' at coordinates {requested!r}"
        )
    if resource_name not in context.resources:
        raise SequenceBundleRuntimeError(
            f"Sequence bundle '{bundle_id}' target resource '{resource_name}' does not exist"
        )
    resource = context.resources[resource_name]
    loader = getattr(resource, "load_sequence", None)
    if not callable(loader):
        raise SequenceBundleRuntimeError(
            f"Sequence bundle '{bundle_id}' target resource '{resource_name}' has no callable load_sequence"
        )
    try:
        selection = bundle_model.resolve(
            requested,
            entry_id=entry_id,
            mode=mode,
            tolerance=tolerance,
        )
    except SequenceBundleResolutionError as exc:
        raise SequenceBundleRuntimeError(
            f"Resource '{resource_name}' could not resolve sequence bundle '{bundle_id}' "
            f"for coordinates {requested!r}: {exc}"
        ) from exc

    _verify_sequence(selection.sequence_file, selection.sequence_sha256, bundle_id, selection.entry_id)
    loader(sequence_file=str(selection.sequence_file))
    _verify_sequence(selection.sequence_file, selection.sequence_sha256, bundle_id, selection.entry_id)

    event_bus.emit(
        SequenceSelected(
            point_id=context.current_point_id,
            coords=context.snapshot_coords(),
            resource=resource_name,
            bundle_id=bundle_id,
            entry_id=selection.entry_id,
            requested_coordinates=dict(selection.requested_coordinates),
            entry_coordinates=dict(selection.entry_coordinates),
            manifest_path=str(selection.manifest_path),
            manifest_sha256=selection.manifest_sha256,
            sequence_file=str(selection.sequence_file),
            sequence_sha256=selection.sequence_sha256,
            metadata=dict(selection.metadata),
        )
    )
    return selection.to_dict()


def _verify_sequence(path: Path, expected_sha256: str, bundle_id: str, entry_id: str) -> None:
    if not path.is_file():
        raise SequenceBundleRuntimeError(
            f"Sequence bundle '{bundle_id}' entry '{entry_id}' file disappeared before load: {path}"
        )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected_sha256:
        raise SequenceBundleRuntimeError(
            f"Sequence bundle '{bundle_id}' entry '{entry_id}' changed after manifest load: {path}; "
            f"expected {expected_sha256}, actual {digest}"
        )
