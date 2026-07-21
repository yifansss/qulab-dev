"""Explicit, provenance-aware sequence generator provider loading."""

from __future__ import annotations

import hashlib
import importlib
import inspect
from pathlib import Path
from typing import Any

from .errors import SequenceGenerationError
from .models import SequenceGeneratorProvider, SourceIdentity


BUILTIN_PROVIDERS = {
    "rabi": "qulab.sequence_generation.providers.experiments.rabi",
    "asg_template": "qulab.sequence_generation.providers.asg_template",
    "ramsey": "qulab.sequence_generation.providers.experiments.ramsey",
    "hahn_echo": "qulab.sequence_generation.providers.experiments.hahn_echo",
}


class SequenceProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, SequenceGeneratorProvider] = {}

    def register(self, name: str, provider: SequenceGeneratorProvider) -> None:
        if not name:
            raise SequenceGenerationError("sequence_provider_not_found", "Provider name cannot be empty")
        self._providers[name] = provider

    def load(self, name: str, version: str | None = None) -> tuple[SequenceGeneratorProvider, SourceIdentity]:
        provider = self._providers.get(name)
        module: Any = None
        if provider is None:
            dotted = BUILTIN_PROVIDERS.get(name, name)
            try:
                module = importlib.import_module(dotted)
            except Exception as exc:
                raise SequenceGenerationError(
                    "sequence_provider_import_failed", f"Could not import sequence provider '{name}': {exc}",
                    context={"provider": name},
                ) from exc
            provider = module.get_provider() if callable(getattr(module, "get_provider", None)) else getattr(module, "PROVIDER", None)
            if provider is None:
                raise SequenceGenerationError(
                    "sequence_provider_not_found", f"Module '{dotted}' does not expose PROVIDER or get_provider()",
                    context={"provider": name},
                )
        try:
            spec = provider.describe()
        except Exception as exc:
            raise SequenceGenerationError(
                "sequence_provider_import_failed", f"Provider '{name}' describe() failed: {exc}", context={"provider": name}
            ) from exc
        if version is not None and str(version) != str(spec.version):
            raise SequenceGenerationError(
                "sequence_provider_version_mismatch",
                f"Provider '{name}' version {spec.version!r} does not match requested {version!r}",
                context={"provider": name, "requested": version, "actual": spec.version},
            )
        source_file = inspect.getsourcefile(module or provider.__class__)
        source_hash = None
        if source_file:
            try:
                source_hash = hashlib.sha256(Path(source_file).read_bytes()).hexdigest()
            except OSError:
                pass
        identity = SourceIdentity(name, str(spec.version), source_file, source_hash)
        return provider, identity

    def descriptors(self) -> tuple[dict[str, Any], ...]:
        """Describe explicitly registered built-ins without directory scanning."""
        result = []
        for name in sorted(BUILTIN_PROVIDERS):
            try:
                provider, identity = self.load(name)
                spec = provider.describe()
                result.append({"id": name, "provider": BUILTIN_PROVIDERS[name], "version": spec.version,
                               "label": spec.label, "description": spec.description,
                               "output_format": spec.output_format, "supports_preview": spec.supports_preview,
                               "source_identity": identity.to_dict()})
            except SequenceGenerationError as exc:
                result.append({"id": name, "provider": BUILTIN_PROVIDERS[name], "error": exc.as_issue().to_dict()})
        return tuple(result)


DEFAULT_PROVIDER_REGISTRY = SequenceProviderRegistry()
