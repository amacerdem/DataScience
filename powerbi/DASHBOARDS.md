# Dashboard Specs — 3 Reports

Each report is a single Power BI page. Build in this order:
Executive (CEO) → Operations (Ops Director) → Customer (CMO).

---

## 1. Executive — "GMV Cockpit"

**Audience**: CEO, opens once a day, looks at top-line in 5 seconds.

**Layout** (16:9 page, dark background optional):

```
┌──────────────────────────────────────────────────────────────────┐
│ Title: Olist — Executive Dashboard                  [Date Slicer]│
├────────┬────────┬────────┬────────┬────────────────────────────┤
│  GMV   │ Orders │  AOV   │  YoY%  │  Active Customers          │
│ KPI    │  KPI   │  KPI   │  KPI   │  KPI                       │
├────────┴────────┴────────┴────────┴────────────────────────────┤
│ GMV by Month — line chart (current YTD vs LY)                    │
├──────────────────────┬───────────────────────────────────────────┤
│ Top 10 Categories    │ Pareto: Cumulative GMV % vs Category Rank │
│ horizontal bar chart │ combo chart (bar + line)                  │
├──────────────────────┴───────────────────────────────────────────┤
│ GMV by Brazilian region — filled map                              │
└──────────────────────────────────────────────────────────────────┘
```

**Visuals & fields**:
1. **Slicer** — `DimDate[year]`, `DimDate[month_name]` (drop-down)
2. **5 KPI cards** — `[GMV]`, `[Order Count]`, `[Average Order Value]`, `[GMV YoY %]`, `[Active Customers]`
3. **Line chart** — Axis: `DimDate[year_month]`, Values: `[GMV]` and `[GMV LY]`
4. **Horizontal bar** — Axis: `DimProduct[category_en]` (Top N=10 by `[GMV]`), Values: `[GMV]`
5. **Combo chart** — Axis: `DimProduct[category_en]` sorted by GMV desc, Bars: `[GMV]`, Line: `[Cumulative GMV %]`
6. **Filled map** — Location: `DimGeography[state]` (Country = "Brazil"), Color saturation: `[GMV]`

---

## 2. Operations — "Delivery & Fulfillment"

**Audience**: Operations Director, monitors logistics SLA daily.

**Layout**:

```
┌──────────────────────────────────────────────────────────────────┐
│ Title: Operations — Delivery Performance      [Date / Region]    │
├──────┬──────┬──────────┬─────────────────────────────────────────┤
│ On-  │ Avg  │ Cancel   │  Delivered Orders                       │
│ Time%│ Days │ Rate     │  KPI                                    │
├──────┴──────┴──────────┴─────────────────────────────────────────┤
│ Delivery Days distribution — histogram                            │
├──────────────────────┬───────────────────────────────────────────┤
│ On-Time % by State   │ Avg Delivery Days — trend (12 months)     │
│ map / heatmap        │ line chart                                │
├──────────────────────┴───────────────────────────────────────────┤
│ Slowest 10 sellers by avg delivery days — table                   │
└──────────────────────────────────────────────────────────────────┘
```

**Visuals & fields**:
1. **KPIs** — `[On-Time Delivery %]`, `[Avg Delivery Days]`, `[Cancellation Rate]`, `[Delivered Orders]`
2. **Histogram** — Bins of `FactOrderItems[delivery_days]` 0-5, 5-10, 10-15, 15-30, 30+
3. **Map** — `DimGeography[state]` colored by `[On-Time Delivery %]`
4. **Line** — Axis: `DimDate[year_month]`, Value: `[Avg Delivery Days]`
5. **Table** — Top 10 by `[Avg Delivery Days]`, columns: seller_id, seller_state, order count, on-time %

---

## 3. Customer — "Acquisition & Retention"

**Audience**: CMO, checks weekly to plan campaigns.

**Layout**:

```
┌──────────────────────────────────────────────────────────────────┐
│ Title: Customer Insights                       [Date / Region]   │
├────────┬────────┬────────┬────────────────────────────────────┤
│ Active │ New    │ Repeat │ Avg Review                          │
│  Cust  │  Cust  │  Cust% │ KPI (with star icons)               │
├────────┴────────┴────────┴────────────────────────────────────┤
│ New vs Returning customers — stacked bar by month                 │
├──────────────────────┬───────────────────────────────────────────┤
│ Customer count by    │ Review score distribution — donut         │
│ state — map          │ (1★, 2★, 3★, 4★, 5★)                      │
├──────────────────────┴───────────────────────────────────────────┤
│ Top 10 categories by avg review score — table                     │
└──────────────────────────────────────────────────────────────────┘
```

**Visuals & fields**:
1. **KPIs** — `[Active Customers]`, `[New Customers]`, `[Repeat Customer %]`, `[Avg Review Score]`
2. **Stacked bar** — Axis: `DimDate[year_month]`, series = New / Returning (calculated columns or measure split)
3. **Map** — `DimCustomer` count by `customer_state`
4. **Donut** — `FactReviews[review_score]` distribution, color by score
5. **Table** — `DimProduct[category_en]` sorted by `[Avg Review Score]` desc, with `[Items Sold]` for weight

---

## Cross-page interactivity

- **Date slicer** at top-right of every page, syncs across pages
- **Region slicer** on Ops + Customer pages, syncs between them only
- **Drill-through**: Right-click any state on map → "Drill through to Operations / Customer"

## Theme & visual hygiene

- One accent color (Olist orange `#FF7E47` or your choice)
- Neutral grey for axes / labels
- Title font: Segoe UI Semibold 14pt
- KPI card: large number 36pt, label 10pt, change-vs-LY 12pt with up/down arrow
- Avoid: 3D charts, pie charts >5 slices, dual y-axis without clear reason
