"""In-memory cache (chip responses + dashboard payloads)."""
from api.cache import Cache


def test_cache_set_and_get():
    cache = Cache()
    cache.set_ask("ciro nedir", {"answer": 42})
    assert cache.get_ask("ciro nedir") == {"answer": 42}


def test_cache_normalizes_question():
    cache = Cache()
    cache.set_ask("Ciro Nedir?", {"answer": 42})
    # case + trailing punctuation insensitive
    assert cache.get_ask("ciro nedir") == {"answer": 42}
    assert cache.get_ask("CIRO NEDIR") == {"answer": 42}


def test_cache_returns_none_on_miss():
    cache = Cache()
    assert cache.get_ask("nonexistent") is None


def test_dashboard_cache():
    cache = Cache()
    cache.set_dashboard("executive", {"kpis": [], "charts": []})
    assert cache.get_dashboard("executive") == {"kpis": [], "charts": []}
