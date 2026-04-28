"""Infer ECharts chart type from a SQL result shape.

Heuristic, not LLM-driven. Cheap + deterministic. The frontend can override
via user picker (Phase 5 polish).
"""
from typing import Any

from api.models import ChartSpec, ResultPayload

GEO_COLUMNS = {"state", "region", "eyalet", "bölge", "bolge"}
DATE_COLUMNS = {"year_month", "month", "date", "ay", "tarih", "yil_ay"}


def _is_numeric(values: list[Any]) -> bool:
    """Check if all values in list are numeric (excluding bool)."""
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values if v is not None)


def infer_chart_spec(result: ResultPayload) -> ChartSpec:
    """Infer chart type from result shape.

    Priority order:
    1. Single value → KPI
    2. Geographic dimension → filled_map
    3. Date/time dimension → line
    4. Categorical + numeric (≤10 rows) → horizontal_bar
    5. Default fallback → table
    """
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
