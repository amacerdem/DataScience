# Olist Demo Presentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-ready interactive web app on top of the existing Olist SQL Server pipeline — Power BI-aesthetic dashboard + Türkçe AI side panel (Claude Opus 4.7 streaming) + `/teknik` boss view, deployed to Vercel.

**Architecture:** Next.js 15 (App Router, React 19) on Vercel ↔ FastAPI backend running locally on the developer's Mac (via Cloudflare Tunnel) ↔ Microsoft SQL Server (Docker, Azure SQL Edge). Two API surfaces: cached chip path (sync JSON) and live LLM path (Server-Sent Events).

**Tech Stack:** Next.js 15 + React 19 + Tailwind v4 + shadcn/ui + Apache ECharts + Framer Motion + Anthropic SDK. Backend: FastAPI + pydantic + pymssql + SQLAlchemy + anthropic. Cloudflare Tunnel for local→Vercel.

**Spec:** [`docs/superpowers/specs/2026-04-28-olist-demo-presentation-design.md`](../specs/2026-04-28-olist-demo-presentation-design.md)

---

## File Structure

### Backend — FastAPI (`api/`)

```
api/
├── main.py                  ← FastAPI app, CORS, mount routers, startup
├── config.py                ← env-driven settings (pydantic-settings)
├── db.py                    ← SQL Server connection pool (pymssql)
├── models.py                ← pydantic request/response models
├── llm.py                   ← Anthropic Claude wrapper (sync + streaming)
├── chart_inference.py       ← infer chart type from result columns/rows
├── routers/
│   ├── ask.py               ← POST /api/ask           (cached)
│   ├── ask_stream.py        ← POST /api/ask/stream    (SSE live)
│   ├── dashboard.py         ← GET  /api/dashboard
│   ├── health.py            ← GET  /api/health
│   └── queries.py           ← GET  /api/queries
├── cache.py                 ← in-memory cache (chip responses + dashboards)
├── precompute.py            ← CLI script: pre-compute chip + dashboard payloads
└── query_log.py             ← in-memory ring buffer of last 20 queries
```

### Frontend — Next.js (`app/`)

```
app/
├── package.json
├── tsconfig.json
├── next.config.ts
├── tailwind.config.ts
├── postcss.config.mjs
├── components.json          ← shadcn config
├── public/
│   └── brazil-states.geo.json     ← IBGE 2022 GeoJSON for ECharts map
├── src/
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── globals.css
│   │   ├── page.tsx                ← / (customer demo)
│   │   └── teknik/page.tsx         ← /teknik (boss view)
│   ├── components/
│   │   ├── ui/                     ← shadcn primitives (button, card, ...)
│   │   ├── dashboard/
│   │   │   ├── DashboardTabs.tsx
│   │   │   ├── KPICard.tsx
│   │   │   ├── ChartCard.tsx
│   │   │   └── ChartRenderer.tsx
│   │   ├── ai/
│   │   │   ├── AIPanel.tsx
│   │   │   ├── SuggestedChips.tsx
│   │   │   ├── ChatBubble.tsx
│   │   │   ├── ChartSkeleton.tsx
│   │   │   └── BehindScenes.tsx
│   │   └── teknik/
│   │       ├── LiveCounter.tsx
│   │       ├── ArchitectureDiagram.tsx
│   │       ├── LayerCard.tsx
│   │       └── QueryLog.tsx
│   └── lib/
│       ├── api.ts                  ← typed fetch wrappers
│       ├── echarts-theme.ts        ← Power BI palette + theme registration
│       ├── chart-presets.ts        ← per-type ECharts option builders
│       └── types.ts                ← TS types mirroring backend models
└── tests/
    ├── chart-inference.test.ts     ← if any pure logic on FE
    └── api-mock.test.ts
```

### Infrastructure (`infrastructure/`)

```
infrastructure/
├── start-all.sh             ← docker + api + tunnel + frontend (1 command)
├── tunnel.sh                ← Cloudflare Tunnel start
├── precompute.sh            ← run api/precompute.py (after pipeline rebuild)
└── README.md                ← deploy instructions
```

---

## Phase 1 — FastAPI Backend Foundation

### Task 1.1: Add backend dependencies and project layout

**Files:**
- Modify: `requirements.txt`
- Create: `api/__init__.py` (empty)
- Create: `api/config.py`
- Create: `api/main.py`

- [ ] **Step 1: Update requirements.txt with backend deps**

```diff
 duckdb>=1.0
 polars>=1.0
 pandas>=2.0
 pyarrow>=15.0
 kaggle>=1.6
 ipykernel
 matplotlib
 python-dotenv
 openai>=1.40
+fastapi>=0.115
+uvicorn[standard]>=0.30
+pydantic>=2.7
+pydantic-settings>=2.5
+sse-starlette>=2.1
+httpx>=0.27
+pytest>=8.0
+pytest-asyncio>=0.24
+anthropic>=0.97
+pymssql>=2.3
+sqlalchemy>=2.0
```

- [ ] **Step 2: Install**

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

Expected: all packages install cleanly.

- [ ] **Step 3: Write `api/config.py`**

```python
"""Centralized settings loaded from environment / .env file."""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Anthropic
    anthropic_api_key: str
    anthropic_model: str = "claude-opus-4-7"

    # SQL Server
    mssql_host: str = "localhost"
    mssql_port: int = 1433
    mssql_user: str = "sa"
    mssql_password: str
    mssql_database: str = "olist"

    # CORS
    allowed_origins: str = "http://localhost:3000,https://olist.show"


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Write `api/main.py` (skeleton)**

```python
"""FastAPI app entry point."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Olist Analytics API", version="1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.allowed_origins.split(",")],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/")
    def root() -> dict[str, str]:
        return {"service": "olist-analytics-api", "status": "ok"}

    return app


app = create_app()
```

- [ ] **Step 5: Smoke run**

```bash
uvicorn api.main:app --reload --port 8000 &
sleep 2
curl -s http://localhost:8000/ | python -m json.tool
kill %1
```

Expected:
```json
{"service": "olist-analytics-api", "status": "ok"}
```

- [ ] **Step 6: Commit**

```bash
git add requirements.txt api/__init__.py api/config.py api/main.py
git commit -m "feat(api): scaffold FastAPI app with config + CORS"
```

---

### Task 1.2: SQL Server connection pool

**Files:**
- Create: `api/db.py`
- Create: `tests/__init__.py` (empty)
- Create: `tests/test_db.py`

- [ ] **Step 1: Write the failing test**

`tests/test_db.py`:
```python
"""SQL Server connectivity smoke tests (require running container)."""
import pytest
from api.db import fetch_df, get_connection


@pytest.mark.integration
def test_connection_returns_version():
    with get_connection() as con:
        cur = con.cursor()
        cur.execute("SELECT @@VERSION")
        row = cur.fetchone()
        assert row is not None
        assert "SQL" in row[0]


@pytest.mark.integration
def test_fetch_df_returns_pandas():
    df = fetch_df("SELECT 1 AS x, 'hello' AS y")
    assert df.shape == (1, 2)
    assert list(df.columns) == ["x", "y"]
    assert df.iloc[0]["x"] == 1
```

- [ ] **Step 2: Run test, verify failure**

```bash
pytest tests/test_db.py -v -m integration
```

Expected: FAIL with `ModuleNotFoundError: No module named 'api.db'`.

- [ ] **Step 3: Write `api/db.py`**

```python
"""SQL Server connection helpers."""
from contextlib import contextmanager
from typing import Iterator

import pandas as pd
import pymssql
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from api.config import get_settings


@contextmanager
def get_connection() -> Iterator[pymssql.Connection]:
    s = get_settings()
    con = pymssql.connect(
        server=s.mssql_host,
        port=s.mssql_port,
        user=s.mssql_user,
        password=s.mssql_password,
        database=s.mssql_database,
    )
    try:
        yield con
    finally:
        con.close()


_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        s = get_settings()
        _engine = create_engine(
            f"mssql+pymssql://{s.mssql_user}:{s.mssql_password}"
            f"@{s.mssql_host}:{s.mssql_port}/{s.mssql_database}",
            pool_size=5,
            pool_pre_ping=True,
        )
    return _engine


def fetch_df(sql: str) -> pd.DataFrame:
    with get_engine().connect() as con:
        return pd.read_sql(sql, con)
```

- [ ] **Step 4: Add pytest marker config**

Create `pyproject.toml` (or update if exists):
```toml
[tool.pytest.ini_options]
markers = [
    "integration: tests that require running services (SQL Server, etc.)",
]
addopts = "-ra"
```

- [ ] **Step 5: Run tests, verify pass**

```bash
docker start mssql  # ensure SQL Server is running
pytest tests/test_db.py -v -m integration
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add api/db.py tests/__init__.py tests/test_db.py pyproject.toml
git commit -m "feat(api): add SQL Server connection pool with pytest"
```

---

### Task 1.3: Pydantic request/response models

**Files:**
- Create: `api/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

`tests/test_models.py`:
```python
"""Pydantic model validation tests."""
import pytest
from pydantic import ValidationError

from api.models import (
    AskRequest,
    ChartSpec,
    AskResponse,
    DashboardTab,
)


def test_ask_request_defaults_to_cache_mode():
    req = AskRequest(question="merhaba")
    assert req.mode == "cache"


def test_ask_request_rejects_empty_question():
    with pytest.raises(ValidationError):
        AskRequest(question="")


def test_chart_spec_horizontal_bar():
    spec = ChartSpec(type="horizontal_bar", x="value", y="label")
    assert spec.type == "horizontal_bar"


def test_chart_spec_rejects_unknown_type():
    with pytest.raises(ValidationError):
        ChartSpec(type="3d_pie_chart_of_doom")


def test_dashboard_tab_enum():
    assert DashboardTab.executive == "executive"
    assert DashboardTab("operations") == DashboardTab.operations
```

- [ ] **Step 2: Run test, verify failure**

```bash
pytest tests/test_models.py -v
```

Expected: FAIL — `api.models` not found.

- [ ] **Step 3: Implement `api/models.py`**

```python
"""Request and response models for the API."""
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

ChartType = Literal[
    "kpi", "horizontal_bar", "vertical_bar", "line", "area",
    "donut", "pie", "scatter", "filled_map", "histogram",
    "pareto_combo", "table",
]


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    mode: Literal["cache", "live"] = "cache"


class ChartSpec(BaseModel):
    type: ChartType
    x: str | None = None
    y: str | None = None
    color: str | None = None
    format: str | None = None
    bins: list[int] | None = None  # for histograms


class ResultPayload(BaseModel):
    columns: list[str]
    rows: list[list[Any]]


class QueryMetadata(BaseModel):
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: dict[str, int]  # {"llm": 1247, "sql": 312, "total": 1559}
    tables_joined: list[str] = []
    cost_usd: float = 0.0


class AskResponse(BaseModel):
    id: str
    source: Literal["cache", "llm"]
    sql: str
    result: ResultPayload
    chart_spec: ChartSpec
    explanation: str
    metadata: QueryMetadata


class DashboardTab(str, Enum):
    executive = "executive"
    operations = "operations"
    customer = "customer"


class KPI(BaseModel):
    label: str
    value: str
    delta: str | None = None  # "↑ 312% YoY" formatted
    delta_kind: Literal["positive", "negative", "neutral"] | None = None


class DashboardChart(BaseModel):
    title: str
    subtitle: str | None = None
    chart_spec: ChartSpec
    result: ResultPayload


class DashboardPayload(BaseModel):
    tab: DashboardTab
    kpis: list[KPI]
    charts: list[DashboardChart]
```

- [ ] **Step 4: Run test, verify pass**

```bash
pytest tests/test_models.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add api/models.py tests/test_models.py
git commit -m "feat(api): pydantic request/response models"
```

---

## Phase 2 — Cache Layer + Pre-built Dashboards

### Task 2.1: Chart type inference

**Files:**
- Create: `api/chart_inference.py`
- Create: `tests/test_chart_inference.py`

- [ ] **Step 1: Write the failing test**

`tests/test_chart_inference.py`:
```python
"""Chart type inference rules."""
from api.chart_inference import infer_chart_spec
from api.models import ResultPayload


def test_single_number_to_kpi():
    res = ResultPayload(columns=["GMV"], rows=[[15840000.00]])
    spec = infer_chart_spec(res)
    assert spec.type == "kpi"


def test_categorical_few_to_horizontal_bar():
    res = ResultPayload(
        columns=["Kategori", "Ciro"],
        rows=[["Health", 1.26e6], ["Watches", 1.21e6], ["Bed", 1.04e6]],
    )
    spec = infer_chart_spec(res)
    assert spec.type == "horizontal_bar"
    assert spec.y == "Kategori"
    assert spec.x == "Ciro"


def test_categorical_many_to_table():
    rows = [[f"cat_{i}", i * 100] for i in range(15)]
    res = ResultPayload(columns=["Kategori", "Ciro"], rows=rows)
    spec = infer_chart_spec(res)
    assert spec.type == "table"


def test_state_column_to_filled_map():
    res = ResultPayload(
        columns=["state", "Ciro"],
        rows=[["SP", 1e6], ["RJ", 8e5], ["MG", 6e5]],
    )
    spec = infer_chart_spec(res)
    assert spec.type == "filled_map"


def test_year_month_to_line():
    res = ResultPayload(
        columns=["year_month", "GMV"],
        rows=[["2017-01", 1e5], ["2017-02", 1.2e5], ["2017-03", 1.5e5]],
    )
    spec = infer_chart_spec(res)
    assert spec.type == "line"
```

- [ ] **Step 2: Run test, verify failure**

```bash
pytest tests/test_chart_inference.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement `api/chart_inference.py`**

```python
"""Infer ECharts chart type from a SQL result shape.

Heuristic, not LLM-driven. Cheap + deterministic. The frontend can override
via user picker (Phase 5 polish).
"""
from typing import Any

from api.models import ChartSpec, ResultPayload

GEO_COLUMNS = {"state", "region", "eyalet", "bölge", "bolge"}
DATE_COLUMNS = {"year_month", "month", "date", "ay", "tarih", "yil_ay"}


def _is_numeric(values: list[Any]) -> bool:
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values if v is not None)


def infer_chart_spec(result: ResultPayload) -> ChartSpec:
    cols = [c.lower() for c in result.columns]
    n_cols = len(result.columns)
    n_rows = len(result.rows)

    # Single value → KPI
    if n_rows == 1 and n_cols == 1:
        return ChartSpec(type="kpi")

    # Geographic dimension present
    if any(c in GEO_COLUMNS for c in cols):
        geo_idx = next(i for i, c in enumerate(cols) if c in GEO_COLUMNS)
        return ChartSpec(
            type="filled_map",
            x=result.columns[geo_idx],
            y=result.columns[1 - geo_idx] if n_cols == 2 else None,
        )

    # Date/time dimension → line chart
    if any(c in DATE_COLUMNS for c in cols):
        date_idx = next(i for i, c in enumerate(cols) if c in DATE_COLUMNS)
        return ChartSpec(
            type="line",
            x=result.columns[date_idx],
            y=result.columns[1 - date_idx] if n_cols == 2 else result.columns[-1],
        )

    # Two cols, first non-numeric (categorical), second numeric → bar
    if n_cols == 2:
        first_vals = [r[0] for r in result.rows]
        second_vals = [r[1] for r in result.rows]
        if not _is_numeric(first_vals) and _is_numeric(second_vals):
            if n_rows <= 10:
                return ChartSpec(type="horizontal_bar", x=result.columns[1], y=result.columns[0])
            return ChartSpec(type="table")

    # Default fallback
    return ChartSpec(type="table")
```

- [ ] **Step 4: Run tests, verify pass**

```bash
pytest tests/test_chart_inference.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add api/chart_inference.py tests/test_chart_inference.py
git commit -m "feat(api): chart type inference from result shape"
```

---

### Task 2.2: In-memory cache module

**Files:**
- Create: `api/cache.py`
- Create: `tests/test_cache.py`

- [ ] **Step 1: Write the failing test**

`tests/test_cache.py`:
```python
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
```

- [ ] **Step 2: Run test, verify failure**

```bash
pytest tests/test_cache.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implement `api/cache.py`**

```python
"""Process-local in-memory cache for chip responses and dashboard payloads.

For demo purposes; in production this would be Redis or similar.
"""
import re
from typing import Any


def _normalize(q: str) -> str:
    q = q.strip().lower()
    q = re.sub(r"[?!.,;:]+$", "", q)
    q = re.sub(r"\s+", " ", q)
    return q


class Cache:
    def __init__(self) -> None:
        self._ask: dict[str, dict[str, Any]] = {}
        self._dashboard: dict[str, dict[str, Any]] = {}

    def set_ask(self, question: str, payload: dict[str, Any]) -> None:
        self._ask[_normalize(question)] = payload

    def get_ask(self, question: str) -> dict[str, Any] | None:
        return self._ask.get(_normalize(question))

    def set_dashboard(self, tab: str, payload: dict[str, Any]) -> None:
        self._dashboard[tab] = payload

    def get_dashboard(self, tab: str) -> dict[str, Any] | None:
        return self._dashboard.get(tab)

    def keys_ask(self) -> list[str]:
        return list(self._ask.keys())


# module singleton
_cache = Cache()


def get_cache() -> Cache:
    return _cache
```

- [ ] **Step 4: Run tests, verify pass**

```bash
pytest tests/test_cache.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add api/cache.py tests/test_cache.py
git commit -m "feat(api): in-memory cache with question normalization"
```

---

### Task 2.3: Cached `POST /api/ask` endpoint

**Files:**
- Create: `api/routers/__init__.py` (empty)
- Create: `api/routers/ask.py`
- Modify: `api/main.py`
- Create: `tests/test_ask.py`

- [ ] **Step 1: Write the failing test**

`tests/test_ask.py`:
```python
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
```

- [ ] **Step 2: Run test, verify failure**

```bash
pytest tests/test_ask.py -v
```

Expected: FAIL — 404 on missing endpoint.

- [ ] **Step 3: Implement `api/routers/ask.py`**

```python
"""Cached chip path — synchronous JSON response from in-memory cache."""
from fastapi import APIRouter, HTTPException

from api.cache import get_cache
from api.models import AskRequest

router = APIRouter()


@router.post("/api/ask")
def ask_cached(req: AskRequest) -> dict:
    cache = get_cache()
    payload = cache.get_ask(req.question)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail="No cached answer; use /api/ask/stream for live LLM",
        )
    return payload
```

- [ ] **Step 4: Wire router into `api/main.py`**

Modify `api/main.py` `create_app()`:
```python
from api.routers import ask as ask_router

# ...inside create_app(), after CORS:
    app.include_router(ask_router.router)
```

- [ ] **Step 5: Run tests, verify pass**

```bash
pytest tests/test_ask.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add api/routers/__init__.py api/routers/ask.py api/main.py tests/test_ask.py
git commit -m "feat(api): cached /api/ask endpoint with chip lookup"
```

---

### Task 2.4: Dashboard payload endpoint

**Files:**
- Create: `api/routers/dashboard.py`
- Modify: `api/main.py`
- Create: `tests/test_dashboard.py`

- [ ] **Step 1: Write the failing test**

`tests/test_dashboard.py`:
```python
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
```

- [ ] **Step 2: Run test, verify failure**

```bash
pytest tests/test_dashboard.py -v
```

- [ ] **Step 3: Implement `api/routers/dashboard.py`**

```python
"""Pre-built dashboard payloads (cached at startup via precompute.py)."""
from fastapi import APIRouter, HTTPException

from api.cache import get_cache
from api.models import DashboardTab

router = APIRouter()


@router.get("/api/dashboard")
def dashboard(tab: DashboardTab) -> dict:
    cache = get_cache()
    payload = cache.get_dashboard(tab.value)
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail=f"Dashboard cache empty for tab '{tab.value}'. Run precompute.py.",
        )
    return payload
```

- [ ] **Step 4: Wire into `api/main.py`**

Add to imports: `from api.routers import ask as ask_router, dashboard as dashboard_router`
Add to `create_app()`: `app.include_router(dashboard_router.router)`

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_dashboard.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add api/routers/dashboard.py api/main.py tests/test_dashboard.py
git commit -m "feat(api): /api/dashboard endpoint with cached payloads"
```

---

### Task 2.5: Pre-compute script for chips + dashboards

**Files:**
- Create: `api/precompute.py`
- Create: `infrastructure/precompute.sh`

- [ ] **Step 1: Write `api/precompute.py`**

```python
"""Pre-compute chip responses and dashboard payloads against SQL Server.

Run after pipeline rebuild to populate the in-memory cache snapshot, then
serialize to data/cache.json. Backend loads this on startup.

    python -m api.precompute
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from api.chart_inference import infer_chart_spec
from api.db import fetch_df
from api.models import (
    AskResponse,
    ChartSpec,
    DashboardChart,
    DashboardPayload,
    DashboardTab,
    KPI,
    QueryMetadata,
    ResultPayload,
)

ROOT = Path(__file__).resolve().parents[1]
CACHE_FILE = ROOT / "data" / "cache.json"

# === CHIP QUESTIONS ===
# (Türkçe soru, T-SQL sorgusu, kısa Türkçe açıklama, üst-üste gelen tablolar)
CHIPS: list[tuple[str, str, str, list[str]]] = [
    (
        "2017 Black Friday cirosu",
        """SELECT d.[year_month] AS [Ay], ROUND(SUM(f.total_value), 2) AS [Ciro]
           FROM gold.FactOrderItems f
           JOIN gold.DimDate d ON f.purchase_date_key = d.date_key
           WHERE d.[year] = 2017
           GROUP BY d.[year_month]
           ORDER BY d.[year_month]""",
        "Kasım 2017'de Black Friday spike'ı 1.18M BRL'ye ulaşıyor.",
        ["gold.FactOrderItems", "gold.DimDate"],
    ),
    (
        "En çok satan 10 kategori",
        """SELECT TOP (10) p.category_en AS [Kategori], ROUND(SUM(f.total_value), 2) AS [Ciro]
           FROM gold.FactOrderItems f
           JOIN gold.DimProduct p ON f.product_key = p.product_key
           GROUP BY p.category_en
           ORDER BY [Ciro] DESC""",
        "Sağlık & Güzellik 1.26M BRL ile lider.",
        ["gold.FactOrderItems", "gold.DimProduct"],
    ),
    (
        "Bölgelere göre ciro karşılaştırması",
        """SELECT g.region AS [Bölge], ROUND(SUM(f.total_value), 2) AS [Ciro]
           FROM gold.FactOrderItems f
           JOIN gold.DimCustomer c ON f.customer_key = c.customer_key
           JOIN gold.DimGeography g ON c.customer_state = g.state
           GROUP BY g.region
           ORDER BY [Ciro] DESC""",
        "Güneydoğu (SP+RJ+MG+ES) toplam cironun %62'sini oluşturuyor.",
        ["gold.FactOrderItems", "gold.DimCustomer", "gold.DimGeography"],
    ),
    (
        "Brezilya bölgelerine göre teslim performansı",
        """SELECT g.region AS [Bölge],
                  ROUND(AVG(CAST(f.delivery_days AS FLOAT)), 1) AS [Ort. Gün],
                  ROUND(AVG(CAST(f.on_time_flag AS FLOAT)) * 100, 2) AS [Zamanında %]
           FROM gold.FactOrderItems f
           JOIN gold.DimCustomer c ON f.customer_key = c.customer_key
           JOIN gold.DimGeography g ON c.customer_state = g.state
           WHERE f.delivery_days IS NOT NULL
           GROUP BY g.region
           ORDER BY [Zamanında %] ASC""",
        "Güney %93.2 zamanında, Kuzeydoğu %85.9 — 7+ puan fark.",
        ["gold.FactOrderItems", "gold.DimCustomer", "gold.DimGeography"],
    ),
    (
        "En yavaş teslimat yapan 10 satıcı",
        """SELECT TOP (10) s.seller_state AS [Eyalet],
                  s.seller_id AS [Satıcı],
                  COUNT(*) AS [Sipariş],
                  ROUND(AVG(CAST(f.delivery_days AS FLOAT)), 1) AS [Ort. Gün]
           FROM gold.FactOrderItems f
           JOIN gold.DimSeller s ON f.seller_key = s.seller_key
           WHERE f.delivery_days IS NOT NULL
           GROUP BY s.seller_state, s.seller_id
           HAVING COUNT(*) >= 10
           ORDER BY [Ort. Gün] DESC""",
        "En yavaş 10 satıcının ortalaması 35+ gün.",
        ["gold.FactOrderItems", "gold.DimSeller"],
    ),
    (
        "Hangi eyalette en çok sipariş iptali var",
        """SELECT TOP (10) c.customer_state AS [Eyalet],
                  COUNT(*) AS [İptal]
           FROM gold.FactOrderItems f
           JOIN gold.DimCustomer c ON f.customer_key = c.customer_key
           WHERE f.order_status = 'canceled'
           GROUP BY c.customer_state
           ORDER BY [İptal] DESC""",
        "SP açık ara önde — hacme bağlı, oran olarak dengeli.",
        ["gold.FactOrderItems", "gold.DimCustomer"],
    ),
    (
        "Repeat customer oranı bölge bazında",
        """SELECT g.region AS [Bölge],
                  COUNT(DISTINCT c.customer_key) AS [Müşteri],
                  ROUND(SUM(CAST(c.is_repeat_customer AS FLOAT)) * 100.0 / COUNT(*), 2) AS [Tekrar %]
           FROM gold.DimCustomer c
           JOIN gold.DimGeography g ON c.customer_state = g.state
           GROUP BY g.region
           ORDER BY [Tekrar %] DESC""",
        "Tüm bölgelerde %3 altı — Olist katalog tabanlı, repeat zayıf.",
        ["gold.DimCustomer", "gold.DimGeography"],
    ),
    (
        "Hangi kategoride 5 yıldız oranı en yüksek",
        """SELECT TOP (10) p.category_en AS [Kategori],
                  COUNT(*) AS [Yorum],
                  ROUND(SUM(CASE WHEN r.review_score = 5 THEN 1.0 ELSE 0 END) * 100.0 / COUNT(*), 2) AS [5★ %]
           FROM gold.FactReviews r
           JOIN gold.FactOrderItems f ON r.order_id = f.order_id
           JOIN gold.DimProduct p ON f.product_key = p.product_key
           GROUP BY p.category_en
           HAVING COUNT(*) >= 100
           ORDER BY [5★ %] DESC""",
        "Books — Imported 79% beş yıldız.",
        ["gold.FactReviews", "gold.FactOrderItems", "gold.DimProduct"],
    ),
    (
        "Kredi kartı vs boleto kullanan müşteri farkı",
        """SELECT p.payment_type AS [Ödeme Tipi],
                  COUNT(DISTINCT p.order_id) AS [Sipariş],
                  ROUND(SUM(p.payment_value) / COUNT(DISTINCT p.order_id), 2) AS [Ortalama Sepet]
           FROM gold.FactPayments p
           WHERE p.payment_type IN ('credit_card', 'boleto')
           GROUP BY p.payment_type
           ORDER BY [Sipariş] DESC""",
        "Kredi kartı 76K sipariş 163.94 BRL ortalama; boleto 20K / 145.03 BRL.",
        ["gold.FactPayments"],
    ),
]


def precompute_chips() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for question, sql, explanation, tables in CHIPS:
        t0 = time.perf_counter()
        df = fetch_df(sql)
        sql_ms = int((time.perf_counter() - t0) * 1000)

        result = ResultPayload(
            columns=list(df.columns),
            rows=[list(r) for r in df.itertuples(index=False, name=None)],
        )
        spec = infer_chart_spec(result)

        resp = AskResponse(
            id=f"q_{uuid.uuid4().hex[:8]}",
            source="cache",
            sql=sql.strip(),
            result=result,
            chart_spec=spec,
            explanation=explanation,
            metadata=QueryMetadata(
                model="cache",
                latency_ms={"sql": sql_ms, "total": sql_ms},
                tables_joined=tables,
            ),
        )
        out[question] = resp.model_dump()
        print(f"  ✓ {question}  ({sql_ms}ms, {result.rows.__len__()} rows)")
    return out


def precompute_dashboards() -> dict[str, dict]:
    """Build Executive / Operations / Customer payloads.

    Each tab assembles KPIs (single SELECT each) + 3-4 charts.
    Implementation: lookup by chip-style queries already cached if available,
    otherwise issue dedicated SQL.
    """
    return {
        "executive": _build_executive(),
        "operations": _build_operations(),
        "customer": _build_customer(),
    }


def _kpi_query(sql: str, label: str, fmt: str = "{:,.2f}") -> KPI:
    df = fetch_df(sql)
    val = df.iloc[0, 0]
    return KPI(label=label, value=fmt.format(val) if isinstance(val, (int, float)) else str(val))


def _build_executive() -> dict:
    kpis = [
        _kpi_query("SELECT SUM(total_value) FROM gold.FactOrderItems", "GMV (BRL)", "R$ {:,.0f}"),
        _kpi_query("SELECT COUNT(DISTINCT order_id) FROM gold.FactOrderItems", "Sipariş", "{:,}"),
        _kpi_query("SELECT SUM(total_value) / COUNT(DISTINCT order_id) FROM gold.FactOrderItems", "AOV", "R$ {:,.2f}"),
        _kpi_query("SELECT COUNT(DISTINCT customer_key) FROM gold.FactOrderItems", "Aktif Müşteri", "{:,}"),
        _kpi_query("SELECT AVG(CAST(CASE WHEN review_score = 5 THEN 1.0 ELSE 0 END AS FLOAT)) * 100 FROM gold.FactReviews", "5★ Oranı", "{:.1f}%"),
    ]
    charts: list[DashboardChart] = []
    return DashboardPayload(tab=DashboardTab.executive, kpis=kpis, charts=charts).model_dump()


def _build_operations() -> dict:
    kpis = [
        _kpi_query(
            "SELECT AVG(CAST(on_time_flag AS FLOAT)) * 100 FROM gold.FactOrderItems WHERE delivery_days IS NOT NULL",
            "Zamanında %", "{:.1f}%"),
        _kpi_query(
            "SELECT AVG(CAST(delivery_days AS FLOAT)) FROM gold.FactOrderItems WHERE delivery_days IS NOT NULL",
            "Ort. Teslim Günü", "{:.1f}"),
        _kpi_query(
            "SELECT COUNT(*) * 100.0 / (SELECT COUNT(*) FROM gold.FactOrderItems) FROM gold.FactOrderItems WHERE order_status = 'canceled'",
            "İptal Oranı", "{:.2f}%"),
        _kpi_query(
            "SELECT COUNT(*) FROM gold.FactOrderItems WHERE order_status = 'delivered'",
            "Teslim Edilen", "{:,}"),
    ]
    return DashboardPayload(tab=DashboardTab.operations, kpis=kpis, charts=[]).model_dump()


def _build_customer() -> dict:
    kpis = [
        _kpi_query("SELECT COUNT(DISTINCT customer_key) FROM gold.FactOrderItems", "Aktif Müşteri", "{:,}"),
        _kpi_query(
            "SELECT COUNT(*) FROM gold.DimCustomer WHERE n_orders_per_unique = 1",
            "Tek Siparişli", "{:,}"),
        _kpi_query(
            "SELECT AVG(CAST(is_repeat_customer AS FLOAT)) * 100 FROM gold.DimCustomer",
            "Tekrar Müşteri %", "{:.2f}%"),
        _kpi_query("SELECT AVG(CAST(review_score AS FLOAT)) FROM gold.FactReviews", "Ort. Puan", "{:.2f}"),
    ]
    return DashboardPayload(tab=DashboardTab.customer, kpis=kpis, charts=[]).model_dump()


def main() -> None:
    print("Pre-computing chips...")
    chips = precompute_chips()
    print(f"\nPre-computing dashboards...")
    dashboards = precompute_dashboards()

    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps({"chips": chips, "dashboards": dashboards}, ensure_ascii=False, default=str, indent=2))
    print(f"\nWrote {CACHE_FILE} ({CACHE_FILE.stat().st_size // 1024}KB)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write `infrastructure/precompute.sh`**

```bash
#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
source .venv/bin/activate
python -m api.precompute
```

- [ ] **Step 3: Make executable + run**

```bash
chmod +x infrastructure/precompute.sh
docker start mssql
./infrastructure/precompute.sh
```

Expected: 9 chip queries pre-computed, 3 dashboards built, `data/cache.json` written (~50-150KB).

- [ ] **Step 4: Commit**

```bash
git add api/precompute.py infrastructure/precompute.sh
git commit -m "feat(api): precompute script for chip + dashboard cache"
```

---

### Task 2.6: Cache loader at startup

**Files:**
- Modify: `api/main.py`
- Create: `tests/test_main_startup.py`

- [ ] **Step 1: Write the failing test**

`tests/test_main_startup.py`:
```python
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
    client = TestClient(app)

    r = client.post("/api/ask", json={"question": "merhaba", "mode": "cache"})
    assert r.status_code == 200
```

- [ ] **Step 2: Run test, verify failure**

```bash
pytest tests/test_main_startup.py -v
```

- [ ] **Step 3: Add startup loader to `api/main.py`**

Replace `create_app()`:
```python
"""FastAPI app entry point."""
import json
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.cache import get_cache
from api.config import get_settings
from api.routers import ask as ask_router, dashboard as dashboard_router

ROOT = Path(__file__).resolve().parents[1]


def _load_cache_file() -> None:
    cache_path = Path(os.environ.get("CACHE_FILE", str(ROOT / "data" / "cache.json")))
    if not cache_path.exists():
        return
    payload = json.loads(cache_path.read_text())
    cache = get_cache()
    for q, p in payload.get("chips", {}).items():
        cache.set_ask(q, p)
    for tab, p in payload.get("dashboards", {}).items():
        cache.set_dashboard(tab, p)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Olist Analytics API", version="1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.allowed_origins.split(",")],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def _startup() -> None:
        _load_cache_file()

    @app.get("/")
    def root() -> dict[str, str]:
        return {"service": "olist-analytics-api", "status": "ok"}

    app.include_router(ask_router.router)
    app.include_router(dashboard_router.router)

    return app


app = create_app()
```

- [ ] **Step 4: Run tests, verify pass**

```bash
pytest tests/test_main_startup.py -v
```

- [ ] **Step 5: Commit**

```bash
git add api/main.py tests/test_main_startup.py
git commit -m "feat(api): load chip+dashboard cache on startup from data/cache.json"
```

---

## Phase 3 — Live LLM Streaming Endpoint

### Task 3.1: Anthropic Claude wrapper (sync + streaming)

**Files:**
- Create: `api/llm.py`
- Create: `tests/test_llm.py`

- [ ] **Step 1: Write the failing test**

`tests/test_llm.py`:
```python
import pytest

from api.llm import build_system_prompt, parse_llm_output


def test_build_system_prompt_includes_t_sql_dialect():
    prompt = build_system_prompt()
    assert "T-SQL" in prompt
    assert "gold.FactOrderItems" in prompt
    assert "Türkçe" in prompt


def test_parse_llm_output_handles_markdown_fence():
    raw = "```sql\nSELECT 1\n```"
    assert parse_llm_output(raw) == "SELECT 1"


def test_parse_llm_output_strips_trailing_semicolon():
    assert parse_llm_output("SELECT 1;") == "SELECT 1"


def test_parse_llm_output_passthrough():
    assert parse_llm_output("SELECT * FROM t") == "SELECT * FROM t"
```

- [ ] **Step 2: Run, verify failure**

```bash
pytest tests/test_llm.py -v
```

- [ ] **Step 3: Implement `api/llm.py`**

```python
"""Anthropic Claude wrapper — reuses prompt + glossary from llm/schema.py."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from llm.schema import SYSTEM_PROMPT  # noqa: E402

from api.config import get_settings


def build_system_prompt() -> str:
    return SYSTEM_PROMPT


def parse_llm_output(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:sql|tsql|mssql)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.rstrip(";").strip()


def get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=get_settings().anthropic_api_key)


def stream_sql(question: str):
    """Yield text deltas from Claude as they arrive. Final yield is full SQL."""
    s = get_settings()
    client = get_client()
    kwargs = dict(
        model=s.anthropic_model,
        max_tokens=2048,
        system=build_system_prompt(),
        messages=[{"role": "user", "content": question.strip()}],
    )
    if s.anthropic_model.startswith(("claude-opus-4-7", "claude-opus-4-6", "claude-sonnet-4-6")):
        kwargs["thinking"] = {"type": "adaptive"}
        kwargs["output_config"] = {"effort": "high"}

    accumulated = []
    with client.messages.stream(**kwargs) as stream:
        for text in stream.text_stream:
            accumulated.append(text)
            yield {"type": "text_delta", "text": text}
        final = stream.get_final_message()

    full_text = "".join(accumulated)
    sql = parse_llm_output(full_text)
    yield {
        "type": "complete",
        "sql": sql,
        "tokens_in": final.usage.input_tokens,
        "tokens_out": final.usage.output_tokens,
        "model": final.model,
    }
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_llm.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add api/llm.py tests/test_llm.py
git commit -m "feat(api): Claude Opus 4.7 streaming wrapper"
```

---

### Task 3.2: SQL safety validator

**Files:**
- Create: `api/sql_validator.py`
- Create: `tests/test_sql_validator.py`

- [ ] **Step 1: Write the failing test**

`tests/test_sql_validator.py`:
```python
import pytest
from api.sql_validator import SQLValidationError, validate_select_only


def test_select_passes():
    validate_select_only("SELECT * FROM gold.FactOrderItems")


def test_with_cte_passes():
    validate_select_only("WITH x AS (SELECT 1) SELECT * FROM x")


def test_insert_rejected():
    with pytest.raises(SQLValidationError):
        validate_select_only("INSERT INTO bronze.foo VALUES (1)")


def test_drop_rejected():
    with pytest.raises(SQLValidationError):
        validate_select_only("DROP TABLE bronze.orders")


def test_truncate_rejected():
    with pytest.raises(SQLValidationError):
        validate_select_only("TRUNCATE TABLE silver.orders")


def test_xp_rejected():
    with pytest.raises(SQLValidationError):
        validate_select_only("EXEC xp_cmdshell 'whoami'")
```

- [ ] **Step 2: Run, verify failure**

```bash
pytest tests/test_sql_validator.py -v
```

- [ ] **Step 3: Implement `api/sql_validator.py`**

```python
"""Reject any SQL that isn't a pure SELECT/WITH read."""
import re


class SQLValidationError(ValueError):
    pass


_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|MERGE|GRANT|REVOKE|EXEC|EXECUTE|XP_)\b",
    re.IGNORECASE,
)
_LEADER = re.compile(r"^\s*(WITH|SELECT)\b", re.IGNORECASE)


def validate_select_only(sql: str) -> None:
    if _FORBIDDEN.search(sql):
        raise SQLValidationError(f"Reddedildi (yazma/yan etki): {sql[:80]}")
    if not _LEADER.match(sql):
        raise SQLValidationError("Sadece SELECT/WITH ile başlayan sorgu kabul edilir.")
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_sql_validator.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add api/sql_validator.py tests/test_sql_validator.py
git commit -m "feat(api): SQL safety validator (SELECT/WITH only)"
```

---

### Task 3.3: SSE streaming endpoint `POST /api/ask/stream`

**Files:**
- Create: `api/routers/ask_stream.py`
- Modify: `api/main.py`
- Create: `api/query_log.py`

- [ ] **Step 1: Write `api/query_log.py`**

```python
"""In-memory ring buffer of last 20 queries for /teknik view."""
from collections import deque
from threading import Lock


class QueryLog:
    def __init__(self, capacity: int = 20) -> None:
        self._buf: deque[dict] = deque(maxlen=capacity)
        self._lock = Lock()

    def add(self, entry: dict) -> None:
        with self._lock:
            self._buf.appendleft(entry)

    def all(self) -> list[dict]:
        with self._lock:
            return list(self._buf)


_log = QueryLog()


def get_log() -> QueryLog:
    return _log
```

- [ ] **Step 2: Implement `api/routers/ask_stream.py`**

```python
"""Live LLM path — Server-Sent Events stream.

Event order:
  skeleton   {id, chart_spec_hint}
  text_delta {text} * N
  sql        {sql}
  result     {columns, rows, chart_spec}
  done       {metadata}
or:
  error      {message}
"""
from __future__ import annotations

import json
import time
import uuid
from typing import AsyncIterator

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from api.chart_inference import infer_chart_spec
from api.db import fetch_df
from api.llm import stream_sql
from api.models import AskRequest, ResultPayload
from api.query_log import get_log
from api.sql_validator import SQLValidationError, validate_select_only

# Opus 4.7 pricing per 1M tokens
COST_IN = 5.00 / 1_000_000
COST_OUT = 25.00 / 1_000_000


router = APIRouter()


def _event(event: str, data: dict) -> dict:
    return {"event": event, "data": json.dumps(data, ensure_ascii=False, default=str)}


@router.post("/api/ask/stream")
async def ask_stream(req: AskRequest) -> EventSourceResponse:
    qid = f"q_{uuid.uuid4().hex[:8]}"

    async def generator() -> AsyncIterator[dict]:
        t_start = time.perf_counter()
        yield _event("skeleton", {"id": qid, "chart_spec_hint": {"type": "unknown"}})

        # 1. Stream Claude tokens
        sql = ""
        tokens_in = tokens_out = 0
        model = ""
        t_llm0 = time.perf_counter()
        try:
            for event in stream_sql(req.question):
                if event["type"] == "text_delta":
                    yield _event("text_delta", {"text": event["text"]})
                elif event["type"] == "complete":
                    sql = event["sql"]
                    tokens_in = event["tokens_in"]
                    tokens_out = event["tokens_out"]
                    model = event["model"]
        except Exception as e:
            yield _event("error", {"message": f"LLM hata: {e}"})
            return
        llm_ms = int((time.perf_counter() - t_llm0) * 1000)

        # 2. Validate SQL
        try:
            validate_select_only(sql)
        except SQLValidationError as e:
            yield _event("error", {"message": str(e)})
            return

        yield _event("sql", {"sql": sql})

        # 3. Execute
        t_sql0 = time.perf_counter()
        try:
            df = fetch_df(sql)
        except Exception as e:
            yield _event("error", {"message": f"SQL hata: {e}"})
            return
        sql_ms = int((time.perf_counter() - t_sql0) * 1000)

        result = ResultPayload(
            columns=list(df.columns),
            rows=[list(r) for r in df.itertuples(index=False, name=None)],
        )
        spec = infer_chart_spec(result)

        yield _event("result", {
            "columns": result.columns,
            "rows": result.rows,
            "chart_spec": spec.model_dump(),
        })

        total_ms = int((time.perf_counter() - t_start) * 1000)
        cost = tokens_in * COST_IN + tokens_out * COST_OUT
        metadata = {
            "id": qid,
            "model": model,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "latency_ms": {"llm": llm_ms, "sql": sql_ms, "total": total_ms},
            "cost_usd": round(cost, 6),
        }
        yield _event("done", {"metadata": metadata})

        # 4. Log to ring buffer
        get_log().add({
            "id": qid,
            "question": req.question,
            "sql": sql,
            "ts": time.time(),
            "metadata": metadata,
            "n_rows": len(result.rows),
        })

    return EventSourceResponse(generator())
```

- [ ] **Step 3: Wire into `api/main.py`**

```python
from api.routers import ask as ask_router, ask_stream as ask_stream_router, dashboard as dashboard_router
# ...
    app.include_router(ask_stream_router.router)
```

- [ ] **Step 4: Smoke test**

```bash
docker start mssql
uvicorn api.main:app --port 8000 &
sleep 2
curl -N -X POST http://localhost:8000/api/ask/stream \
  -H "Content-Type: application/json" \
  -d '{"question":"2017 yılında en çok satan 3 kategori","mode":"live"}'
kill %1
```

Expected: SSE events stream — `skeleton`, `text_delta` × N, `sql`, `result`, `done`.

- [ ] **Step 5: Commit**

```bash
git add api/routers/ask_stream.py api/query_log.py api/main.py
git commit -m "feat(api): /api/ask/stream SSE endpoint with Claude streaming"
```

---

## Phase 4 — Health + Queries Endpoints

### Task 4.1: Health endpoint with live pipeline metrics

**Files:**
- Create: `api/routers/health.py`
- Modify: `api/main.py`
- Create: `tests/test_health.py`

- [ ] **Step 1: Write the failing test**

`tests/test_health.py`:
```python
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


def test_health_returns_required_keys():
    r = client.get("/api/health")
    assert r.status_code in (200, 503)
    if r.status_code == 200:
        body = r.json()
        assert "sql_server" in body
        assert "rows" in body
        assert "uptime_minutes" in body
```

- [ ] **Step 2: Run, verify failure**

- [ ] **Step 3: Implement `api/routers/health.py`**

```python
"""Live pipeline metrics for /teknik header counter."""
import time
from typing import Any

from fastapi import APIRouter, HTTPException

from api.db import fetch_df
from api.query_log import get_log

router = APIRouter()
_started = time.time()


@router.get("/api/health")
def health() -> dict[str, Any]:
    try:
        version_df = fetch_df("SELECT @@VERSION AS v")
        version = str(version_df.iloc[0, 0])
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"SQL Server unreachable: {e}")

    rows_df = fetch_df("""
        SELECT s.name + '.' + t.name AS tbl, p.rows AS n
        FROM sys.tables t
        JOIN sys.schemas s ON t.schema_id = s.schema_id
        JOIN sys.partitions p ON t.object_id = p.object_id
        WHERE p.index_id IN (0,1)
          AND s.name IN ('bronze','silver','gold')
    """)
    rows_by_layer = {"bronze": 0, "silver": 0, "gold": 0}
    for _, r in rows_df.iterrows():
        layer = r["tbl"].split(".")[0]
        rows_by_layer[layer] += int(r["n"])

    last = get_log().all()[:1]
    return {
        "sql_server": {"status": "online", "version": version[:80]},
        "rows": rows_by_layer,
        "last_query": last[0] if last else None,
        "uptime_minutes": int((time.time() - _started) / 60),
    }
```

- [ ] **Step 4: Wire into `api/main.py`**

```python
from api.routers import ask as ask_router, ask_stream as ask_stream_router, dashboard as dashboard_router, health as health_router
# ...
    app.include_router(health_router.router)
```

- [ ] **Step 5: Run tests**

```bash
docker start mssql
pytest tests/test_health.py -v
```

- [ ] **Step 6: Commit**

```bash
git add api/routers/health.py api/main.py tests/test_health.py
git commit -m "feat(api): /api/health with row counts + uptime"
```

---

### Task 4.2: Queries log endpoint

**Files:**
- Create: `api/routers/queries.py`
- Modify: `api/main.py`

- [ ] **Step 1: Implement `api/routers/queries.py`**

```python
"""Last 20 queries for /teknik query log table."""
from fastapi import APIRouter

from api.query_log import get_log

router = APIRouter()


@router.get("/api/queries")
def queries() -> dict:
    return {"items": get_log().all()}
```

- [ ] **Step 2: Wire into main.py**

```python
from api.routers import ask as ask_router, ask_stream as ask_stream_router, dashboard as dashboard_router, health as health_router, queries as queries_router
# ...
    app.include_router(queries_router.router)
```

- [ ] **Step 3: Smoke test**

```bash
curl -s http://localhost:8000/api/queries | python -m json.tool
```

Expected: `{"items": []}` (empty until queries are made).

- [ ] **Step 4: Commit**

```bash
git add api/routers/queries.py api/main.py
git commit -m "feat(api): /api/queries log endpoint"
```

---

## Phase 5 — Next.js Scaffold + Power BI Design System

### Task 5.1: Create Next.js app

**Files:**
- Create: `app/` (entire Next.js project tree)

- [ ] **Step 1: Scaffold Next.js**

```bash
cd "Data-Science-Company/olist-pipeline"
npx -y create-next-app@latest app \
  --typescript --app --tailwind --eslint --src-dir --import-alias "@/*" \
  --use-npm --turbo
```

Choose defaults; the script generates the full tree.

- [ ] **Step 2: Verify dev server**

```bash
cd app
npm run dev &
sleep 5
curl -s http://localhost:3000 -o /dev/null -w "%{http_code}\n"
kill %1
```

Expected: `200`.

- [ ] **Step 3: Install runtime deps**

```bash
cd app
npm install \
  echarts echarts-for-react \
  framer-motion \
  lucide-react \
  zustand \
  clsx \
  tailwind-merge
```

- [ ] **Step 4: Init shadcn/ui**

```bash
npx -y shadcn@latest init -d
# Choose: Default style, Slate base color
```

- [ ] **Step 5: Install shadcn components used in the app**

```bash
npx -y shadcn@latest add button card tabs sheet badge skeleton input scroll-area separator
```

- [ ] **Step 6: Commit**

```bash
cd ..
git add app/
git commit -m "feat(app): scaffold Next.js 15 with shadcn + ECharts + Framer"
```

---

### Task 5.2: Power BI design tokens (Tailwind theme)

**Files:**
- Modify: `app/src/app/globals.css`
- Modify: `app/tailwind.config.ts`

- [ ] **Step 1: Replace `app/src/app/globals.css`**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --background: 0 0% 98%;          /* #FAFAFA */
    --foreground: 0 0% 14%;          /* #252525 */
    --card: 0 0% 100%;               /* #FFFFFF */
    --card-foreground: 0 0% 14%;
    --primary: 211 100% 53%;          /* #118DFF */
    --primary-foreground: 0 0% 100%;
    --accent: 28 100% 50%;            /* #FF8C00 */
    --success: 120 75% 27%;           /* #107C10 */
    --warning: 44 100% 49%;           /* #FDB900 */
    --danger: 357 60% 40%;            /* #A4262C */
    --muted: 0 0% 91%;                /* #E8E8E8 */
    --muted-foreground: 0 0% 35%;     /* #595959 */
    --border: 0 0% 91%;
    --input: 0 0% 91%;
    --ring: 211 100% 53%;
    --radius: 0.5rem;
  }
}

@layer base {
  body {
    @apply bg-background text-foreground;
    font-family: 'Segoe UI Variable', 'Segoe UI', -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
    font-feature-settings: "ss01" 1, "cv01" 1;
  }

  .kpi-number {
    @apply text-2xl font-bold tracking-tight;
  }

  .kpi-label {
    @apply text-[11px] font-semibold uppercase tracking-wider text-muted-foreground;
  }

  .pbi-card {
    @apply bg-card border border-border rounded-lg p-4 shadow-[0_1px_2px_rgba(0,0,0,0.04)] hover:shadow-[0_2px_8px_rgba(0,0,0,0.08)] transition-shadow;
  }
}
```

- [ ] **Step 2: Update `app/tailwind.config.ts`**

```ts
import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        card: { DEFAULT: 'hsl(var(--card))', foreground: 'hsl(var(--card-foreground))' },
        primary: { DEFAULT: 'hsl(var(--primary))', foreground: 'hsl(var(--primary-foreground))' },
        accent: 'hsl(var(--accent))',
        success: 'hsl(var(--success))',
        warning: 'hsl(var(--warning))',
        danger: 'hsl(var(--danger))',
        muted: { DEFAULT: 'hsl(var(--muted))', foreground: 'hsl(var(--muted-foreground))' },
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
      },
      borderRadius: { lg: 'var(--radius)', md: 'calc(var(--radius) - 2px)', sm: 'calc(var(--radius) - 4px)' },
    },
  },
  plugins: [],
};
export default config;
```

- [ ] **Step 3: Visual sanity check**

Modify `app/src/app/page.tsx` temporarily to render `<div class="pbi-card kpi-number">R$ 15.84M</div>`, run dev, verify card renders white with correct typography. Revert before commit.

- [ ] **Step 4: Commit**

```bash
git add app/src/app/globals.css app/tailwind.config.ts
git commit -m "feat(app): Power BI Fluent design tokens (light theme)"
```

---

### Task 5.3: ECharts Power BI theme

**Files:**
- Create: `app/src/lib/echarts-theme.ts`
- Create: `app/public/brazil-states.geo.json`

- [ ] **Step 1: Download Brazil GeoJSON**

```bash
curl -L -o app/public/brazil-states.geo.json \
  https://raw.githubusercontent.com/codeforgermany/click_that_hood/main/public/data/brazil-states.geojson
```

Verify size > 50 KB:
```bash
ls -la app/public/brazil-states.geo.json
```

- [ ] **Step 2: Implement `app/src/lib/echarts-theme.ts`**

```ts
import * as echarts from 'echarts/core';

export const POWERBI_PALETTE = [
  '#118DFF', '#FF8C00', '#107C10', '#FDB900',
  '#A4262C', '#5C2D91', '#0078D4', '#498205',
];

export const POWERBI_THEME_NAME = 'powerbi';

export function registerPowerBITheme() {
  echarts.registerTheme(POWERBI_THEME_NAME, {
    color: POWERBI_PALETTE,
    backgroundColor: '#FFFFFF',
    textStyle: { fontFamily: "'Segoe UI Variable', 'Segoe UI', system-ui" },
    title: { textStyle: { color: '#252525', fontWeight: 600, fontSize: 13 } },
    grid: { left: '6%', right: '4%', top: 32, bottom: 28, containLabel: true },
    categoryAxis: { axisLine: { lineStyle: { color: '#E8E8E8' } }, axisTick: { show: false }, axisLabel: { color: '#595959' }, splitLine: { show: false } },
    valueAxis:    { axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: '#595959' }, splitLine: { lineStyle: { color: '#F0F0F0' } } },
    legend: { textStyle: { color: '#595959', fontSize: 11 } },
    tooltip: { backgroundColor: '#FFFFFF', borderColor: '#E8E8E8', borderWidth: 1, textStyle: { color: '#252525' }, padding: [8, 12] },
  });
}
```

- [ ] **Step 3: Commit**

```bash
git add app/src/lib/echarts-theme.ts app/public/brazil-states.geo.json
git commit -m "feat(app): ECharts Power BI theme + Brazil GeoJSON"
```

---

### Task 5.4: API client + types

**Files:**
- Create: `app/src/lib/types.ts`
- Create: `app/src/lib/api.ts`

- [ ] **Step 1: Implement `app/src/lib/types.ts`** (mirror backend models)

```ts
export type ChartType =
  | 'kpi' | 'horizontal_bar' | 'vertical_bar' | 'line' | 'area'
  | 'donut' | 'pie' | 'scatter' | 'filled_map' | 'histogram'
  | 'pareto_combo' | 'table';

export interface ChartSpec {
  type: ChartType;
  x?: string | null;
  y?: string | null;
  color?: string | null;
  format?: string | null;
  bins?: number[] | null;
}

export interface ResultPayload {
  columns: string[];
  rows: Array<Array<string | number | null>>;
}

export interface QueryMetadata {
  model: string;
  tokens_in: number;
  tokens_out: number;
  latency_ms: { llm?: number; sql?: number; total: number };
  tables_joined: string[];
  cost_usd: number;
}

export interface AskResponse {
  id: string;
  source: 'cache' | 'llm';
  sql: string;
  result: ResultPayload;
  chart_spec: ChartSpec;
  explanation: string;
  metadata: QueryMetadata;
}

export type DashboardTab = 'executive' | 'operations' | 'customer';

export interface KPI {
  label: string;
  value: string;
  delta?: string | null;
  delta_kind?: 'positive' | 'negative' | 'neutral' | null;
}

export interface DashboardChart {
  title: string;
  subtitle?: string | null;
  chart_spec: ChartSpec;
  result: ResultPayload;
}

export interface DashboardPayload {
  tab: DashboardTab;
  kpis: KPI[];
  charts: DashboardChart[];
}

export interface HealthPayload {
  sql_server: { status: 'online' | 'offline'; version: string };
  rows: { bronze: number; silver: number; gold: number };
  last_query: { id: string; ts: number; metadata: { latency_ms: { total: number } } } | null;
  uptime_minutes: number;
}
```

- [ ] **Step 2: Implement `app/src/lib/api.ts`**

```ts
import type { AskResponse, DashboardPayload, DashboardTab, HealthPayload } from './types';

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? 'http://localhost:8000';

export async function askCached(question: string): Promise<AskResponse> {
  const r = await fetch(`${BASE}/api/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, mode: 'cache' }),
  });
  if (!r.ok) throw new Error(`/api/ask ${r.status}`);
  return r.json();
}

export async function fetchDashboard(tab: DashboardTab): Promise<DashboardPayload> {
  const r = await fetch(`${BASE}/api/dashboard?tab=${tab}`);
  if (!r.ok) throw new Error(`/api/dashboard ${r.status}`);
  return r.json();
}

export async function fetchHealth(): Promise<HealthPayload> {
  const r = await fetch(`${BASE}/api/health`);
  if (!r.ok) throw new Error(`/api/health ${r.status}`);
  return r.json();
}

export type StreamEvent =
  | { type: 'skeleton'; id: string }
  | { type: 'text_delta'; text: string }
  | { type: 'sql'; sql: string }
  | { type: 'result'; columns: string[]; rows: any[][]; chart_spec: any }
  | { type: 'done'; metadata: any }
  | { type: 'error'; message: string };

export async function* askStream(question: string): AsyncIterable<StreamEvent> {
  const r = await fetch(`${BASE}/api/ask/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, mode: 'live' }),
  });
  if (!r.ok || !r.body) throw new Error(`/api/ask/stream ${r.status}`);

  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });

    while (true) {
      const sep = buf.indexOf('\n\n');
      if (sep < 0) break;
      const block = buf.slice(0, sep);
      buf = buf.slice(sep + 2);

      let event = 'message';
      let data = '';
      for (const line of block.split('\n')) {
        if (line.startsWith('event: ')) event = line.slice(7).trim();
        else if (line.startsWith('data: ')) data += line.slice(6);
      }
      if (!data) continue;
      try {
        const parsed = JSON.parse(data);
        yield { type: event as any, ...parsed };
      } catch {
        // skip malformed
      }
    }
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add app/src/lib/types.ts app/src/lib/api.ts
git commit -m "feat(app): API client + TS types mirroring backend"
```

---

## Phase 6 — Customer Demo Page

### Task 6.1: ChartRenderer (the workhorse)

**Files:**
- Create: `app/src/lib/chart-presets.ts`
- Create: `app/src/components/dashboard/ChartRenderer.tsx`

- [ ] **Step 1: Implement `app/src/lib/chart-presets.ts`**

```ts
import type { ChartSpec, ResultPayload } from './types';
import brazilGeo from '../../public/brazil-states.geo.json';
import { POWERBI_PALETTE } from './echarts-theme';

export function buildOption(spec: ChartSpec, result: ResultPayload): any {
  switch (spec.type) {
    case 'horizontal_bar': return horizontalBar(spec, result);
    case 'vertical_bar':   return verticalBar(spec, result);
    case 'line':           return lineChart(spec, result);
    case 'area':           return lineChart(spec, result, true);
    case 'donut':          return donut(spec, result);
    case 'filled_map':     return filledMap(spec, result);
    case 'histogram':      return histogram(spec, result);
    case 'pareto_combo':   return paretoCombo(spec, result);
    default:               return null;  // table / kpi handled by other components
  }
}

function horizontalBar(spec: ChartSpec, r: ResultPayload) {
  const labels = r.rows.map(row => row[r.columns.indexOf(spec.y!)]);
  const values = r.rows.map(row => row[r.columns.indexOf(spec.x!)]);
  return {
    grid: { left: 100, right: 24, top: 8, bottom: 24 },
    xAxis: { type: 'value' },
    yAxis: { type: 'category', data: labels.reverse(), axisLabel: { fontSize: 11 } },
    series: [{ type: 'bar', data: [...values].reverse(), itemStyle: { color: POWERBI_PALETTE[0], borderRadius: [0, 2, 2, 0] }, barWidth: 18 }],
    tooltip: { trigger: 'axis' },
  };
}

function verticalBar(spec: ChartSpec, r: ResultPayload) {
  const labels = r.rows.map(row => row[r.columns.indexOf(spec.x!)]);
  const values = r.rows.map(row => row[r.columns.indexOf(spec.y!)]);
  return {
    xAxis: { type: 'category', data: labels, axisLabel: { fontSize: 10 } },
    yAxis: { type: 'value' },
    series: [{ type: 'bar', data: values, itemStyle: { color: POWERBI_PALETTE[0], borderRadius: [2, 2, 0, 0] } }],
    tooltip: { trigger: 'axis' },
  };
}

function lineChart(spec: ChartSpec, r: ResultPayload, area = false) {
  const labels = r.rows.map(row => String(row[r.columns.indexOf(spec.x!)]));
  const values = r.rows.map(row => row[r.columns.indexOf(spec.y!)]);
  return {
    xAxis: { type: 'category', data: labels, boundaryGap: false },
    yAxis: { type: 'value' },
    series: [{ type: 'line', smooth: true, data: values, lineStyle: { color: POWERBI_PALETTE[0], width: 2 }, itemStyle: { color: POWERBI_PALETTE[0] }, areaStyle: area ? { color: POWERBI_PALETTE[0], opacity: 0.15 } : undefined }],
    tooltip: { trigger: 'axis' },
  };
}

function donut(_spec: ChartSpec, r: ResultPayload) {
  const data = r.rows.map(row => ({ name: String(row[0]), value: Number(row[1]) }));
  return {
    series: [{
      type: 'pie', radius: ['55%', '80%'], avoidLabelOverlap: true, data,
      label: { fontSize: 11, color: '#252525' },
    }],
    tooltip: { trigger: 'item' },
  };
}

function filledMap(_spec: ChartSpec, r: ResultPayload) {
  if (typeof window !== 'undefined') {
    const echarts = require('echarts/core');
    echarts.registerMap('Brazil', brazilGeo as any);
  }
  const data = r.rows.map(row => ({ name: String(row[0]), value: Number(row[1]) }));
  const max = Math.max(...data.map(d => d.value));
  return {
    visualMap: { min: 0, max, calculable: true, text: ['Yüksek', 'Düşük'], inRange: { color: ['#E5F2FF', POWERBI_PALETTE[0]] }, textStyle: { fontSize: 10 } },
    series: [{ type: 'map', map: 'Brazil', data, label: { show: false }, emphasis: { label: { show: true, fontSize: 10 } } }],
    tooltip: { trigger: 'item' },
  };
}

function histogram(_spec: ChartSpec, r: ResultPayload) {
  return verticalBar({ type: 'vertical_bar', x: r.columns[0], y: r.columns[1] }, r);
}

function paretoCombo(_spec: ChartSpec, r: ResultPayload) {
  const labels = r.rows.map(row => String(row[0]));
  const values = r.rows.map(row => Number(row[1]));
  const total = values.reduce((a, b) => a + b, 0);
  let cum = 0;
  const cumPct = values.map(v => { cum += v; return (cum / total) * 100; });
  return {
    xAxis: { type: 'category', data: labels, axisLabel: { fontSize: 10, rotate: 30 } },
    yAxis: [
      { type: 'value', name: 'Ciro' },
      { type: 'value', name: '%', max: 100, axisLabel: { formatter: '{value}%' } },
    ],
    series: [
      { type: 'bar', data: values, itemStyle: { color: POWERBI_PALETTE[0] } },
      { type: 'line', yAxisIndex: 1, data: cumPct, smooth: true, lineStyle: { color: POWERBI_PALETTE[1] } },
    ],
    tooltip: { trigger: 'axis' },
  };
}
```

- [ ] **Step 2: Implement `ChartRenderer.tsx`**

```tsx
'use client';

import { useEffect, useRef } from 'react';
import * as echarts from 'echarts/core';
import { BarChart, LineChart, PieChart, MapChart } from 'echarts/charts';
import { GridComponent, TooltipComponent, LegendComponent, VisualMapComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import ReactECharts from 'echarts-for-react/lib/core';

import { buildOption } from '@/lib/chart-presets';
import { registerPowerBITheme, POWERBI_THEME_NAME } from '@/lib/echarts-theme';
import type { ChartSpec, ResultPayload } from '@/lib/types';

echarts.use([BarChart, LineChart, PieChart, MapChart, GridComponent, TooltipComponent, LegendComponent, VisualMapComponent, CanvasRenderer]);

export function ChartRenderer({ spec, result, height = 280 }: { spec: ChartSpec; result: ResultPayload; height?: number }) {
  const initialized = useRef(false);
  useEffect(() => {
    if (!initialized.current) {
      registerPowerBITheme();
      initialized.current = true;
    }
  }, []);

  if (spec.type === 'table') {
    return (
      <div className="overflow-auto" style={{ maxHeight: height }}>
        <table className="w-full text-[11px]">
          <thead>
            <tr className="border-b border-border">
              {result.columns.map(c => <th key={c} className="text-left px-2 py-1 text-muted-foreground font-semibold">{c}</th>)}
            </tr>
          </thead>
          <tbody>
            {result.rows.map((r, i) => (
              <tr key={i} className="border-b border-border/50">
                {r.map((v, j) => <td key={j} className="px-2 py-1">{v == null ? '—' : String(v)}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  const option = buildOption(spec, result);
  if (!option) return <div className="text-xs text-muted-foreground p-4">Chart type not supported: {spec.type}</div>;

  return (
    <ReactECharts
      echarts={echarts}
      option={option}
      theme={POWERBI_THEME_NAME}
      style={{ height, width: '100%' }}
      opts={{ renderer: 'canvas' }}
    />
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add app/src/lib/chart-presets.ts app/src/components/dashboard/ChartRenderer.tsx
git commit -m "feat(app): ChartRenderer with 7 ECharts presets + table fallback"
```

---

### Task 6.2: KPICard component

**Files:**
- Create: `app/src/components/dashboard/KPICard.tsx`

- [ ] **Step 1: Implement**

```tsx
import { ArrowUp, ArrowDown, Minus } from 'lucide-react';
import { motion } from 'framer-motion';

import type { KPI } from '@/lib/types';
import { cn } from '@/lib/utils';

export function KPICard({ kpi, index = 0 }: { kpi: KPI; index?: number }) {
  const Icon = kpi.delta_kind === 'positive' ? ArrowUp : kpi.delta_kind === 'negative' ? ArrowDown : Minus;
  const deltaColor = kpi.delta_kind === 'positive' ? 'text-success' : kpi.delta_kind === 'negative' ? 'text-danger' : 'text-muted-foreground';
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, delay: index * 0.06, ease: 'easeOut' }}
      className="pbi-card"
    >
      <div className="kpi-label">{kpi.label}</div>
      <div className="kpi-number mt-1">{kpi.value}</div>
      {kpi.delta && (
        <div className={cn('text-[10px] flex items-center gap-1 mt-1', deltaColor)}>
          <Icon className="w-3 h-3" />
          {kpi.delta}
        </div>
      )}
    </motion.div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add app/src/components/dashboard/KPICard.tsx
git commit -m "feat(app): KPICard with Framer Motion entrance"
```

---

### Task 6.3: ChartCard wrapper

**Files:**
- Create: `app/src/components/dashboard/ChartCard.tsx`

- [ ] **Step 1: Implement**

```tsx
import { ChartRenderer } from './ChartRenderer';
import type { DashboardChart } from '@/lib/types';

export function ChartCard({ chart }: { chart: DashboardChart }) {
  return (
    <div className="pbi-card">
      <div>
        <div className="text-[13px] font-semibold text-foreground">{chart.title}</div>
        {chart.subtitle && <div className="text-[10px] text-muted-foreground mt-0.5">{chart.subtitle}</div>}
      </div>
      <div className="mt-3">
        <ChartRenderer spec={chart.chart_spec} result={chart.result} />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add app/src/components/dashboard/ChartCard.tsx
git commit -m "feat(app): ChartCard wrapper"
```

---

### Task 6.4: Dashboard tabs page (`/`)

**Files:**
- Create: `app/src/components/dashboard/DashboardTabs.tsx`
- Modify: `app/src/app/page.tsx`

- [ ] **Step 1: Implement `DashboardTabs.tsx`**

```tsx
'use client';

import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

import { fetchDashboard } from '@/lib/api';
import type { DashboardPayload, DashboardTab } from '@/lib/types';
import { KPICard } from './KPICard';
import { ChartCard } from './ChartCard';

const TABS: { id: DashboardTab; label: string; emoji: string }[] = [
  { id: 'executive', label: 'Executive', emoji: '📊' },
  { id: 'operations', label: 'Operations', emoji: '🚚' },
  { id: 'customer', label: 'Customer', emoji: '👤' },
];

export function DashboardTabs() {
  const [active, setActive] = useState<DashboardTab>('executive');
  const [data, setData] = useState<DashboardPayload | null>(null);

  useEffect(() => {
    setData(null);
    fetchDashboard(active).then(setData).catch(console.error);
  }, [active]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex gap-1 bg-muted rounded-md p-1 w-fit">
        {TABS.map(t => (
          <button key={t.id}
            onClick={() => setActive(t.id)}
            className={`px-3 py-1.5 rounded text-xs font-semibold transition ${active === t.id ? 'bg-card shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}
          >
            {t.emoji} {t.label}
          </button>
        ))}
      </div>

      <AnimatePresence mode="wait">
        <motion.div
          key={active}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="flex flex-col gap-4"
        >
          {data ? (
            <>
              <div className={`grid gap-3 ${data.kpis.length === 5 ? 'grid-cols-5' : 'grid-cols-4'}`}>
                {data.kpis.map((k, i) => <KPICard key={k.label} kpi={k} index={i} />)}
              </div>
              <div className="grid grid-cols-3 gap-3">
                {data.charts.map(c => <ChartCard key={c.title} chart={c} />)}
              </div>
            </>
          ) : (
            <div className="text-xs text-muted-foreground">Yükleniyor...</div>
          )}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
```

- [ ] **Step 2: Modify `app/src/app/page.tsx`**

```tsx
import { DashboardTabs } from '@/components/dashboard/DashboardTabs';

export default function Home() {
  return (
    <div className="min-h-screen flex">
      <main className="flex-1 p-4">
        <header className="flex items-center gap-4 mb-4">
          <div className="font-bold text-primary text-sm">◇ Olist Analytics</div>
        </header>
        <DashboardTabs />
      </main>
      {/* AI panel will be added in Phase 7 */}
    </div>
  );
}
```

- [ ] **Step 3: Run dev server**

```bash
cd app && npm run dev &
sleep 3
open http://localhost:3000
```

Verify Executive tab loads with KPIs (charts empty until Task 7 wires chart payloads in precompute).

- [ ] **Step 4: Commit**

```bash
git add app/src/components/dashboard/DashboardTabs.tsx app/src/app/page.tsx
git commit -m "feat(app): DashboardTabs with 3 tabs + KPI grid"
```

---

## Phase 7 — AI Panel (Conversation + Streaming)

### Task 7.1: Suggested chips component

**Files:**
- Create: `app/src/components/ai/SuggestedChips.tsx`

- [ ] **Step 1: Implement**

```tsx
import type { DashboardTab } from '@/lib/types';

const CHIPS_BY_TAB: Record<DashboardTab, { emoji: string; q: string }[]> = {
  executive: [
    { emoji: '📈', q: '2017 Black Friday cirosu' },
    { emoji: '🏆', q: 'En çok satan 10 kategori' },
    { emoji: '🇧🇷', q: 'Bölgelere göre ciro karşılaştırması' },
  ],
  operations: [
    { emoji: '🚚', q: 'Brezilya bölgelerine göre teslim performansı' },
    { emoji: '⏱', q: 'En yavaş teslimat yapan 10 satıcı' },
    { emoji: '❌', q: 'Hangi eyalette en çok sipariş iptali var' },
  ],
  customer: [
    { emoji: '🔁', q: 'Repeat customer oranı bölge bazında' },
    { emoji: '⭐', q: 'Hangi kategoride 5 yıldız oranı en yüksek' },
    { emoji: '💳', q: 'Kredi kartı vs boleto kullanan müşteri farkı' },
  ],
};

export function SuggestedChips({ tab, onPick }: { tab: DashboardTab; onPick: (q: string) => void }) {
  return (
    <div className="flex flex-col gap-1.5 mt-2">
      {CHIPS_BY_TAB[tab].map(c => (
        <button key={c.q}
          onClick={() => onPick(c.q)}
          className="text-left text-[11px] bg-blue-50 border border-blue-200 text-blue-900 px-2 py-1.5 rounded hover:bg-blue-100 transition"
        >
          {c.emoji} {c.q}
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add app/src/components/ai/SuggestedChips.tsx
git commit -m "feat(app): SuggestedChips with 9 pre-built questions"
```

---

### Task 7.2: ChatBubble + ChartSkeleton + BehindScenes

**Files:**
- Create: `app/src/components/ai/ChatBubble.tsx`
- Create: `app/src/components/ai/ChartSkeleton.tsx`
- Create: `app/src/components/ai/BehindScenes.tsx`

- [ ] **Step 1: Implement `ChartSkeleton.tsx`**

```tsx
import { motion } from 'framer-motion';

export function ChartSkeleton() {
  return (
    <div className="space-y-1.5 mt-2">
      {[0.85, 0.7, 0.55, 0.42].map((w, i) => (
        <motion.div key={i}
          initial={{ width: 0, opacity: 0 }}
          animate={{ width: `${w * 100}%`, opacity: 0.5 }}
          transition={{ duration: 0.4, delay: i * 0.08 }}
          className="h-3 bg-primary/40 rounded-sm"
        />
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Implement `BehindScenes.tsx`**

```tsx
'use client';
import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';

export function BehindScenes({ sql, metadata }: { sql: string; metadata: any }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-2 text-[10px]">
      <button onClick={() => setOpen(!open)} className="flex items-center gap-1 text-muted-foreground hover:text-primary">
        {open ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        🔧 Bu nasıl üretildi?
      </button>
      {open && (
        <div className="mt-1.5 space-y-1.5 border-l-2 border-primary pl-2">
          <pre className="whitespace-pre-wrap font-mono text-[9px] bg-muted/50 p-1.5 rounded">{sql}</pre>
          <div className="text-muted-foreground">
            <span className="font-semibold">Latency:</span> LLM {metadata.latency_ms?.llm ?? 0}ms + SQL {metadata.latency_ms?.sql ?? 0}ms = {metadata.latency_ms?.total}ms
          </div>
          <div className="text-muted-foreground">
            <span className="font-semibold">Tokens:</span> in {metadata.tokens_in} + out {metadata.tokens_out} (${metadata.cost_usd?.toFixed(6)})
          </div>
          <div className="text-muted-foreground">
            <span className="font-semibold">Model:</span> {metadata.model}
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Implement `ChatBubble.tsx`**

```tsx
import { ChartRenderer } from '@/components/dashboard/ChartRenderer';
import { ChartSkeleton } from './ChartSkeleton';
import { BehindScenes } from './BehindScenes';
import type { AskResponse, ChartSpec, ResultPayload } from '@/lib/types';

export type Message =
  | { role: 'user'; text: string }
  | {
      role: 'assistant';
      text: string;
      result?: { columns: string[]; rows: any[][]; spec: ChartSpec };
      sql?: string;
      metadata?: any;
      streaming?: boolean;
    };

export function ChatBubble({ msg }: { msg: Message }) {
  if (msg.role === 'user') {
    return (
      <div className="bg-muted/50 border border-border rounded p-2 text-[11px]">
        <span className="text-muted-foreground text-[9px]">Sen ›</span><br />
        {msg.text}
      </div>
    );
  }

  return (
    <div className="bg-card border border-border border-l-[3px] border-l-primary rounded p-2 text-[11px]">
      <span className="text-primary text-[9px] font-semibold">AI ›</span>
      <div className="mt-1 whitespace-pre-wrap">{msg.text || (msg.streaming ? '...' : '')}</div>
      {msg.result ? (
        <div className="mt-2">
          <ChartRenderer spec={msg.result.spec} result={{ columns: msg.result.columns, rows: msg.result.rows }} height={180} />
        </div>
      ) : msg.streaming ? (
        <ChartSkeleton />
      ) : null}
      {msg.sql && msg.metadata && <BehindScenes sql={msg.sql} metadata={msg.metadata} />}
    </div>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add app/src/components/ai/ChatBubble.tsx app/src/components/ai/ChartSkeleton.tsx app/src/components/ai/BehindScenes.tsx
git commit -m "feat(app): ChatBubble + ChartSkeleton + BehindScenes"
```

---

### Task 7.3: AIPanel (orchestrator)

**Files:**
- Create: `app/src/components/ai/AIPanel.tsx`
- Modify: `app/src/app/page.tsx`

- [ ] **Step 1: Implement `AIPanel.tsx`**

```tsx
'use client';

import { useState } from 'react';
import { Send } from 'lucide-react';

import { askCached, askStream } from '@/lib/api';
import type { DashboardTab } from '@/lib/types';
import { ChatBubble, type Message } from './ChatBubble';
import { SuggestedChips } from './SuggestedChips';

export function AIPanel({ tab }: { tab: DashboardTab }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);

  async function handleChip(q: string) {
    setMessages(m => [...m, { role: 'user', text: q }]);
    setBusy(true);
    try {
      const resp = await askCached(q);
      setMessages(m => [...m, {
        role: 'assistant',
        text: resp.explanation,
        result: { columns: resp.result.columns, rows: resp.result.rows, spec: resp.chart_spec },
        sql: resp.sql,
        metadata: resp.metadata,
      }]);
    } finally {
      setBusy(false);
    }
  }

  async function handleAsk() {
    const q = input.trim();
    if (!q || busy) return;
    setInput('');
    setMessages(m => [...m, { role: 'user', text: q }, { role: 'assistant', text: '', streaming: true }]);
    setBusy(true);
    try {
      let acc = '';
      let sql: string | undefined;
      let result: any;
      let metadata: any;
      for await (const ev of askStream(q)) {
        if (ev.type === 'text_delta') {
          acc += ev.text;
          setMessages(m => updateLast(m, { text: acc }));
        } else if (ev.type === 'sql') {
          sql = ev.sql;
        } else if (ev.type === 'result') {
          result = { columns: ev.columns, rows: ev.rows, spec: ev.chart_spec };
          setMessages(m => updateLast(m, { result }));
        } else if (ev.type === 'done') {
          metadata = ev.metadata;
          setMessages(m => updateLast(m, { sql, metadata, streaming: false }));
        } else if (ev.type === 'error') {
          setMessages(m => updateLast(m, { text: `Hata: ${ev.message}`, streaming: false }));
        }
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <aside className="w-[280px] border-l border-border bg-card p-3 flex flex-col gap-2">
      <div className="flex items-center gap-1.5 font-semibold text-xs">
        <span className="bg-primary text-primary-foreground text-[9px] px-1.5 py-0.5 rounded font-bold">AI</span>
        Türkçe Sor
      </div>
      <div className="text-[10px] text-muted-foreground font-semibold mt-2">Önerilen Sorular</div>
      <SuggestedChips tab={tab} onPick={handleChip} />

      <div className="text-[10px] text-muted-foreground font-semibold mt-3">Konuşma</div>
      <div className="flex flex-col gap-1.5 max-h-[420px] overflow-y-auto">
        {messages.map((m, i) => <ChatBubble key={i} msg={m} />)}
        {messages.length === 0 && <div className="text-[10px] text-muted-foreground italic">Bir chip tıkla veya yaz...</div>}
      </div>

      <div className="mt-auto flex items-center gap-1 border border-input rounded p-1.5 bg-card">
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && !e.shiftKey && handleAsk()}
          placeholder="Bir şey sor..."
          className="flex-1 text-[11px] outline-none bg-transparent"
          disabled={busy}
        />
        <button
          onClick={handleAsk}
          disabled={busy || !input.trim()}
          className="bg-primary text-primary-foreground w-5 h-5 rounded-full flex items-center justify-center disabled:opacity-50"
        >
          <Send className="w-3 h-3" />
        </button>
      </div>
    </aside>
  );
}

function updateLast(m: Message[], patch: Partial<Extract<Message, { role: 'assistant' }>>): Message[] {
  if (m.length === 0) return m;
  const last = m[m.length - 1];
  if (last.role !== 'assistant') return m;
  return [...m.slice(0, -1), { ...last, ...patch }];
}
```

- [ ] **Step 2: Wire AIPanel into `app/src/app/page.tsx`**

```tsx
'use client';

import { useState } from 'react';
import { DashboardTabs } from '@/components/dashboard/DashboardTabs';
import { AIPanel } from '@/components/ai/AIPanel';
import type { DashboardTab } from '@/lib/types';

export default function Home() {
  const [tab, setTab] = useState<DashboardTab>('executive');

  return (
    <div className="min-h-screen flex">
      <main className="flex-1 p-4 max-w-[calc(100vw-280px)]">
        <header className="flex items-center gap-4 mb-4">
          <div className="font-bold text-primary text-sm">◇ Olist Analytics</div>
        </header>
        <DashboardTabs onTabChange={setTab} />
      </main>
      <AIPanel tab={tab} />
    </div>
  );
}
```

(Note: `DashboardTabs` needs to expose `onTabChange`; modify if not already.)

- [ ] **Step 3: Update `DashboardTabs` to emit tab change**

```diff
-export function DashboardTabs() {
-  const [active, setActive] = useState<DashboardTab>('executive');
+export function DashboardTabs({ onTabChange }: { onTabChange?: (tab: DashboardTab) => void }) {
+  const [active, setActive] = useState<DashboardTab>('executive');
+
+  function pickTab(t: DashboardTab) {
+    setActive(t);
+    onTabChange?.(t);
+  }
```

Replace `setActive(t.id)` calls with `pickTab(t.id)`.

- [ ] **Step 4: Smoke test (manual, dev server)**

```bash
docker start mssql
uvicorn api.main:app --port 8000 &
cd app && npm run dev &
sleep 5
open http://localhost:3000
```

Test flow:
1. Click "📈 2017 Black Friday cirosu" chip → cached response with chart appears.
2. Type "2017 yılında en çok satan 5 kategori" + Enter → SSE streaming visible (text fills, then chart).
3. Click "🔧 Bu nasıl üretildi?" → SQL + latency + tokens shown.

- [ ] **Step 5: Commit**

```bash
git add app/src/components/ai/AIPanel.tsx app/src/app/page.tsx app/src/components/dashboard/DashboardTabs.tsx
git commit -m "feat(app): AIPanel with chip + live LLM streaming + behind-scenes"
```

---

## Phase 8 — `/teknik` Boss View

### Task 8.1: LiveCounter (polls /api/health)

**Files:**
- Create: `app/src/components/teknik/LiveCounter.tsx`

- [ ] **Step 1: Implement**

```tsx
'use client';

import { useEffect, useState } from 'react';
import { fetchHealth } from '@/lib/api';
import type { HealthPayload } from '@/lib/types';

export function LiveCounter() {
  const [health, setHealth] = useState<HealthPayload | null>(null);

  useEffect(() => {
    let stop = false;
    async function poll() {
      try { const h = await fetchHealth(); if (!stop) setHealth(h); } catch {}
      setTimeout(poll, 5000);
    }
    poll();
    return () => { stop = true; };
  }, []);

  if (!health) return <div className="text-xs text-muted-foreground">Loading metrics...</div>;

  const total = health.rows.bronze + health.rows.silver + health.rows.gold;
  const lastMs = health.last_query?.metadata?.latency_ms?.total ?? 0;

  return (
    <div className="grid grid-cols-4 gap-3 text-xs">
      <Cell label="Total Rows" value={total.toLocaleString()} />
      <Cell label="SQL Server" value={health.sql_server.status} kind={health.sql_server.status === 'online' ? 'success' : 'danger'} />
      <Cell label="Last Query" value={lastMs ? `${lastMs}ms` : '—'} />
      <Cell label="Uptime" value={`${health.uptime_minutes}m`} />
    </div>
  );
}

function Cell({ label, value, kind }: { label: string; value: string; kind?: 'success' | 'danger' }) {
  return (
    <div className="pbi-card">
      <div className="kpi-label">{label}</div>
      <div className={`kpi-number mt-1 ${kind === 'success' ? 'text-success' : kind === 'danger' ? 'text-danger' : ''}`}>{value}</div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add app/src/components/teknik/LiveCounter.tsx
git commit -m "feat(app): LiveCounter polling /api/health every 5s"
```

---

### Task 8.2: ArchitectureDiagram (animated SVG)

**Files:**
- Create: `app/src/components/teknik/ArchitectureDiagram.tsx`

- [ ] **Step 1: Implement** (concise SVG with flowing dot animation between layers)

```tsx
'use client';
import { motion } from 'framer-motion';

export function ArchitectureDiagram() {
  const layers = [
    { y: 30,  w: 360, label: 'Olist CSV (Kaggle)', color: '#8A8A8A' },
    { y: 90,  w: 360, label: 'Bronze (Parquet, 1.55M satır)', color: '#C97D2F' },
    { y: 150, w: 360, label: 'Silver (T-SQL, deduped)', color: '#A0A0A0' },
    { y: 210, w: 360, label: 'Gold (Star schema)', color: '#FDB900' },
    { y: 270, w: 360, label: 'Claude Opus 4.7 (NL→T-SQL)', color: '#118DFF' },
    { y: 330, w: 360, label: 'Frontend (ECharts)', color: '#107C10' },
  ];

  return (
    <svg viewBox="0 0 400 380" className="w-full max-w-md">
      {layers.map((l, i) => (
        <g key={i}>
          <rect x={(400 - l.w) / 2} y={l.y} width={l.w} height={36} rx={6} fill={l.color} opacity={0.9} />
          <text x={200} y={l.y + 22} textAnchor="middle" fill="white" fontSize="12" fontWeight="600">{l.label}</text>
          {i < layers.length - 1 && (
            <motion.circle
              r={4} fill="#118DFF"
              initial={{ cx: 200, cy: l.y + 36 }}
              animate={{ cy: layers[i + 1].y }}
              transition={{ duration: 1.4, repeat: Infinity, delay: i * 0.2, ease: 'easeInOut' }}
            />
          )}
        </g>
      ))}
    </svg>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add app/src/components/teknik/ArchitectureDiagram.tsx
git commit -m "feat(app): animated architecture diagram"
```

---

### Task 8.3: QueryLog table

**Files:**
- Create: `app/src/components/teknik/QueryLog.tsx`

- [ ] **Step 1: Implement**

```tsx
'use client';
import { useEffect, useState } from 'react';

interface QEntry { id: string; question: string; sql: string; ts: number; metadata: any; n_rows: number; }

export function QueryLog() {
  const [items, setItems] = useState<QEntry[]>([]);

  useEffect(() => {
    let stop = false;
    async function poll() {
      try {
        const r = await fetch('http://localhost:8000/api/queries');
        const j = await r.json();
        if (!stop) setItems(j.items);
      } catch {}
      setTimeout(poll, 3000);
    }
    poll();
    return () => { stop = true; };
  }, []);

  if (items.length === 0) return <div className="text-xs text-muted-foreground">Henüz sorgu yok.</div>;

  return (
    <div className="pbi-card overflow-auto">
      <table className="w-full text-[11px]">
        <thead>
          <tr className="border-b border-border text-muted-foreground">
            <th className="text-left px-2 py-1.5">Zaman</th>
            <th className="text-left px-2 py-1.5">Soru</th>
            <th className="text-right px-2 py-1.5">Satır</th>
            <th className="text-right px-2 py-1.5">Latency</th>
            <th className="text-right px-2 py-1.5">Maliyet</th>
          </tr>
        </thead>
        <tbody>
          {items.map(q => (
            <tr key={q.id} className="border-b border-border/50">
              <td className="px-2 py-1.5 text-muted-foreground">{new Date(q.ts * 1000).toLocaleTimeString('tr-TR')}</td>
              <td className="px-2 py-1.5">{q.question.slice(0, 60)}</td>
              <td className="px-2 py-1.5 text-right">{q.n_rows}</td>
              <td className="px-2 py-1.5 text-right">{q.metadata.latency_ms.total}ms</td>
              <td className="px-2 py-1.5 text-right">${q.metadata.cost_usd?.toFixed(5) ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add app/src/components/teknik/QueryLog.tsx
git commit -m "feat(app): QueryLog table polling /api/queries"
```

---

### Task 8.4: `/teknik` page assembly

**Files:**
- Create: `app/src/app/teknik/page.tsx`

- [ ] **Step 1: Implement**

```tsx
import { LiveCounter } from '@/components/teknik/LiveCounter';
import { ArchitectureDiagram } from '@/components/teknik/ArchitectureDiagram';
import { QueryLog } from '@/components/teknik/QueryLog';

export default function TeknikPage() {
  return (
    <div className="min-h-screen p-6 max-w-6xl mx-auto">
      <header className="mb-6">
        <div className="text-xs text-muted-foreground uppercase tracking-wider">Behind the scenes</div>
        <h1 className="text-2xl font-bold mt-1">Olist Pipeline — Mimari ve Çalışan Sistemler</h1>
        <p className="text-sm text-muted-foreground mt-1">Ham CSV'den Power BI'a: T-SQL üretimi, latency, maliyet — şeffaf.</p>
      </header>

      <section className="mb-8">
        <h2 className="text-sm font-semibold mb-3">Canlı Metrikler</h2>
        <LiveCounter />
      </section>

      <section className="mb-8">
        <h2 className="text-sm font-semibold mb-3">Mimari</h2>
        <div className="pbi-card flex items-center justify-center">
          <ArchitectureDiagram />
        </div>
      </section>

      <section className="mb-8">
        <h2 className="text-sm font-semibold mb-3">Son Sorgular</h2>
        <QueryLog />
      </section>
    </div>
  );
}
```

- [ ] **Step 2: Smoke test**

```bash
open http://localhost:3000/teknik
```

Verify all 3 sections render: live counter, architecture, query log.

- [ ] **Step 3: Commit**

```bash
git add app/src/app/teknik/page.tsx
git commit -m "feat(app): /teknik boss view with live metrics + arch + query log"
```

---

## Phase 9 — Deploy

### Task 9.1: Cloudflare Tunnel script

**Files:**
- Create: `infrastructure/tunnel.sh`
- Create: `infrastructure/start-all.sh`
- Create: `infrastructure/README.md`

- [ ] **Step 1: Install cloudflared**

```bash
brew install cloudflared
cloudflared --version
```

- [ ] **Step 2: Implement `infrastructure/tunnel.sh`**

```bash
#!/usr/bin/env bash
set -e
# Ad-hoc TryCloudflare tunnel — outputs https://*.trycloudflare.com URL
echo "Starting Cloudflare Tunnel → http://localhost:8000"
cloudflared tunnel --url http://localhost:8000
```

- [ ] **Step 3: Implement `infrastructure/start-all.sh`**

```bash
#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."

echo "▶ Docker SQL Server"
docker start mssql || docker run -d --name mssql -e ACCEPT_EULA=Y -e MSSQL_SA_PASSWORD="$MSSQL_PASSWORD" -p 1433:1433 mcr.microsoft.com/azure-sql-edge:latest

echo "▶ Activate venv"
source .venv/bin/activate

echo "▶ FastAPI on :8000"
uvicorn api.main:app --port 8000 --reload &
API_PID=$!

echo "▶ Cloudflare Tunnel"
infrastructure/tunnel.sh &
TUNNEL_PID=$!

echo "▶ Next.js on :3000"
(cd app && npm run dev) &
FE_PID=$!

trap "kill $API_PID $TUNNEL_PID $FE_PID 2>/dev/null" EXIT
wait
```

- [ ] **Step 4: Implement `infrastructure/README.md`**

```markdown
# Demo Stack — Local + Tunnel + Vercel

## Quick start (local)

    chmod +x infrastructure/*.sh
    ./infrastructure/start-all.sh

Then open http://localhost:3000.

## Deploy frontend to Vercel

1. Push the `app/` directory to a Vercel project (root: `app/`).
2. Set env: `NEXT_PUBLIC_API_BASE=<trycloudflare-url>`
3. Run tunnel locally: `./infrastructure/tunnel.sh` — note the URL.
4. Update Vercel env with that URL, redeploy.

## Custom domain

`olist.show` (or similar) → CNAME to Vercel.
```

- [ ] **Step 5: Commit**

```bash
chmod +x infrastructure/*.sh
git add infrastructure/
git commit -m "feat(infra): tunnel + start-all + deploy README"
```

---

### Task 9.2: Deploy to Vercel

- [ ] **Step 1: Push to GitHub** (already done — repo at amacerdem/DataScience)

- [ ] **Step 2: Vercel project setup**

Visit https://vercel.com/new → import `amacerdem/DataScience` → set:
- Framework: Next.js
- Root Directory: `app/`
- Build command: `npm run build`
- Install command: `npm install`

- [ ] **Step 3: Run tunnel locally**

```bash
./infrastructure/tunnel.sh
# Copy the https://*.trycloudflare.com URL
```

- [ ] **Step 4: Set Vercel env**

In Vercel project → Settings → Environment Variables:
- `NEXT_PUBLIC_API_BASE` = `<trycloudflare URL>`

Then trigger redeploy.

- [ ] **Step 5: Verify production**

Open the Vercel URL. Test:
1. Dashboard tabs load (KPIs visible)
2. Chip click works (cached response)
3. Live LLM stream works (Türkçe question)
4. `/teknik` shows live row counts

- [ ] **Step 6: Commit and tag**

```bash
git tag -a v1.0-demo -m "First production demo deploy"
git push origin v1.0-demo
```

---

## Self-Review Checklist (run after writing the plan)

- [ ] **Spec coverage:**
  - Goals (Section 1) → covered by Phases 1-9
  - Architecture (Section 2) → Phase 1 backend + Phase 5 frontend + Phase 9 deploy
  - Routes (Section 3) → Phase 6 (`/`) + Phase 8 (`/teknik`)
  - Visual design (Section 4) → Task 5.2 + 5.3
  - Pre-built dashboards (Section 5) → Task 2.5 (precompute) + 6.4 (render)
  - AI conversation (Section 6) → Phase 7 entire
  - Backend API (Section 7) → Phases 2 + 3 + 4
  - Phase 1-6 in spec → Phases 1-8 in plan (renamed for sequencing)
  - Risks (Section 10) → Tasks include error handling at SQL/LLM/SSE boundaries
  - Success criteria (Section 11) → Smoke tests at end of each phase

- [ ] **Placeholders:** None — every task has explicit code, file paths, and commands.

- [ ] **Type consistency:**
  - `ChartType` Literal in models.py → matches `ChartType` in types.ts
  - `AskResponse` fields match between Python pydantic and TS interface
  - SSE event names (`skeleton`, `text_delta`, `sql`, `result`, `done`, `error`) consistent across backend (ask_stream.py) and frontend (api.ts)
  - `DashboardTab` enum: same values in both (`executive` / `operations` / `customer`)

- [ ] **Scope:** 9 phases, ~38 tasks, 2-5 min each = ~3-5 days of focused work. Fits a single plan; no decomposition needed.

---

## Execution Handoff

**Plan complete and saved to** `docs/superpowers/plans/2026-04-28-olist-demo-presentation-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Best for this plan because the tasks span multiple stacks (Python backend, TS frontend, infrastructure) and isolation prevents context bleed.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints. Faster for trivially-related tasks but session context will get heavy by Phase 5+.

**Which approach?**
