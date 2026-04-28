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
