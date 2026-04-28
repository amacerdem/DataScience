import json
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
CACHE_FILE = ROOT / "data" / "cache.json"


def test_cache_loaded_on_startup(tmp_path, monkeypatch):
    fake_cache = tmp_path / "cache.json"
    fake_cache.write_text(json.dumps({
        "chips": {"merhaba": {"id": "x", "source": "cache", "sql": "", "result": {"columns": [], "rows": []}, "chart_spec": {"type": "kpi"}, "explanation": "", "metadata": {"model": "cache", "latency_ms": {"total": 1}}}},
        "dashboards": {"executive": {"tab": "executive", "kpis": [], "charts": []}},
    }))
    monkeypatch.setenv("CACHE_FILE", str(fake_cache))

    from api.main import create_app
    app = create_app()
    with TestClient(app) as client:
        r = client.post("/api/ask", json={"question": "merhaba", "mode": "cache"})
    assert r.status_code == 200
