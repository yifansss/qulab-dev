"""Compatibility import for the canonical curated Rabi provider."""
from .experiments.rabi import PROVIDER, RabiFamilyProvider, get_provider
__all__ = ["PROVIDER", "RabiFamilyProvider", "get_provider"]
