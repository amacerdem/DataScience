"""Process-local in-memory cache for chip responses and dashboard payloads.

For demo purposes; in production this would be Redis or similar.
"""
import re
from typing import Any


def _normalize(q: str) -> str:
    """Normalize question: lowercase, strip trailing punctuation, collapse whitespace."""
    q = q.strip().lower()
    q = re.sub(r"[?!.,;:]+$", "", q)
    q = re.sub(r"\s+", " ", q)
    return q


class Cache:
    """In-memory cache for chip responses and dashboard payloads."""

    def __init__(self) -> None:
        self._ask: dict[str, dict[str, Any]] = {}
        self._dashboard: dict[str, dict[str, Any]] = {}

    def set_ask(self, question: str, payload: dict[str, Any]) -> None:
        """Cache a chip response for a question."""
        self._ask[_normalize(question)] = payload

    def get_ask(self, question: str) -> dict[str, Any] | None:
        """Retrieve cached chip response, or None if not found."""
        return self._ask.get(_normalize(question))

    def set_dashboard(self, tab: str, payload: dict[str, Any]) -> None:
        """Cache a dashboard payload for a tab."""
        self._dashboard[tab] = payload

    def get_dashboard(self, tab: str) -> dict[str, Any] | None:
        """Retrieve cached dashboard payload, or None if not found."""
        return self._dashboard.get(tab)

    def keys_ask(self) -> list[str]:
        """Return list of cached question keys."""
        return list(self._ask.keys())


# module singleton
_cache = Cache()


def get_cache() -> Cache:
    """Get the module-level cache singleton."""
    return _cache
