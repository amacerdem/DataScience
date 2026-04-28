from fastapi.testclient import TestClient

from api.cache import get_cache
from api.main import app

client = TestClient(app)


def test_ask_cache_hit_returns_payload():
    cache = get_cache()
    cache.set_ask("merhaba", {
        "id": "q_x",
        "source": "cache",
        "sql": "SELECT 1",
        "result": {"columns": ["x"], "rows": [[1]]},
        "chart_spec": {"type": "kpi"},
        "explanation": "ok",
        "metadata": {"model": "cache", "latency_ms": {"total": 5}},
    })
    r = client.post("/api/ask", json={"question": "merhaba", "mode": "cache"})
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "cache"
    assert body["sql"] == "SELECT 1"


def test_ask_cache_miss_returns_404():
    r = client.post("/api/ask", json={"question": "askjdhakjsd", "mode": "cache"})
    assert r.status_code == 404


def test_ask_validation_rejects_empty_question():
    r = client.post("/api/ask", json={"question": "", "mode": "cache"})
    assert r.status_code == 422
