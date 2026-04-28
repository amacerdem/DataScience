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
