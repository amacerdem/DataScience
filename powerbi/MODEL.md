# Power BI Semantic Model — Olist Star Schema

## Build steps (Power BI Desktop, ~10 minutes)

1. **Get Data → Folder** → point to `data/gold/` (Power Query reads Parquet natively)
2. Promote each Parquet file to its own table — keep names exactly:
   `DimDate`, `DimCustomer`, `DimProduct`, `DimSeller`, `DimGeography`,
   `FactOrderItems`, `FactPayments`, `FactReviews`, `_bridge_customer`
3. In Power Query: hide `_bridge_customer` from client view (right-click → Properties → "Hide in report view")
4. Click **Close & Apply**
5. Switch to **Model view** and create relationships per the table below
6. Mark `DimDate` as a date table (Modeling → Mark as date table → `DimDate[date]`)
7. Apply formatting per the "Column formatting" section
8. Paste DAX measures from `MEASURES.dax`

## Relationships

All relationships are **single-direction**, **many-to-one** (fact → dim).

| From (many side)              | To (one side)            | Active |
|-------------------------------|--------------------------|--------|
| FactOrderItems[purchase_date_key]   | DimDate[date_key]        | ✓ active |
| FactOrderItems[delivered_date_key]  | DimDate[date_key]        | inactive (USERELATIONSHIP) |
| FactOrderItems[customer_key]        | DimCustomer[customer_key]| ✓ |
| FactOrderItems[product_key]         | DimProduct[product_key]  | ✓ |
| FactOrderItems[seller_key]          | DimSeller[seller_key]    | ✓ |
| DimCustomer[customer_state]         | DimGeography[state]      | ✓ |
| FactPayments[purchase_date_key]     | DimDate[date_key]        | ✓ |
| FactPayments[customer_key]          | DimCustomer[customer_key]| ✓ |
| FactReviews[purchase_date_key]      | DimDate[date_key]        | ✓ |
| FactReviews[customer_key]           | DimCustomer[customer_key]| ✓ |
| FactOrderItems[order_id]            | FactReviews[order_id]    | inactive (do NOT activate) |

## Column formatting

| Column                              | Type     | Format          |
|-------------------------------------|----------|-----------------|
| Fact*[price], [freight_value], [total_value], [payment_value] | Decimal  | "R$ #,0.00"     |
| Fact*[*_date_key]                   | Whole #  | hide from client |
| Fact*[customer_key], [product_key], [seller_key] | Whole #  | hide from client |
| FactOrderItems[delivery_days], [delivery_vs_estimate_days] | Whole # | "0 days" |
| FactOrderItems[on_time_flag]        | Whole #  | hide (used by measure) |
| FactReviews[review_score]           | Whole #  | "0" (1-5 star)  |
| DimDate[date_key]                   | Whole #  | hide            |
| DimDate[date]                       | Date     | "yyyy-MM-dd"    |
| DimDate[year_month]                 | Text     | sort by date_key |

## Hide from client view

Hide these from report consumers:
- All `_key` columns on facts
- All `_date_key` columns
- `FactOrderItems[on_time_flag]` (replaced by % measure)
- `_bridge_customer` (entire table)

## Hierarchies

- **DimDate**: Year → Quarter → Month → Day
- **DimGeography → DimCustomer**: Region → State → City (via relationship)
- **DimProduct**: Category → Product

## Display folders (group measures in the field list)

- Sales
- Customers
- Operations
- Reviews
- Time Intelligence
