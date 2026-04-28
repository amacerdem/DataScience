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
