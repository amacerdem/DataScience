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
        print(f"  ✓ {question}  ({sql_ms}ms, {len(result.rows)} rows)")
    return out


def precompute_dashboards() -> dict[str, dict]:
    """Build Executive / Operations / Customer payloads."""
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
    CACHE_FILE.write_text(
        json.dumps({"chips": chips, "dashboards": dashboards}, ensure_ascii=False, default=str, indent=2)
    )
    print(f"\nWrote {CACHE_FILE} ({CACHE_FILE.stat().st_size // 1024}KB)")


if __name__ == "__main__":
    main()
