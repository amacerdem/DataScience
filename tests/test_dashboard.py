from fastapi.testclient import TestClient

from api.cache import get_cache
from api.main import app

client = TestClient(app)


def test_dashboard_executive_returns_cached_payload():
    cache = get_cache()
    cache.set_dashboard("executive", {
        "tab": "executive",
        "kpis": [{"label": "GMV", "value": "R$ 15.84M", "delta": "↑ 312%", "delta_kind": "positive"}],
        "charts": [],
    })
    r = client.get("/api/dashboard?tab=executive")
    assert r.status_code == 200
    body = r.json()
    assert body["tab"] == "executive"
    assert body["kpis"][0]["label"] == "GMV"


def test_dashboard_unknown_tab_returns_422():
    r = client.get("/api/dashboard?tab=foo")
    assert r.status_code == 422


def test_dashboard_no_cache_returns_503():
    cache = get_cache()
    if "operations" in cache._dashboard:
        del cache._dashboard["operations"]
    r = client.get("/api/dashboard?tab=operations")
    assert r.status_code == 503
