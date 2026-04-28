"""Bronze layer — ingest raw Olist CSVs into immutable Parquet files.

Convention:
- Read each CSV with explicit dtype to avoid pandas inference surprises
- Add ingestion metadata: _ingested_at, _source_file
- Write as Parquet (snappy) — Delta-Lake compatible, columnar, ~10x smaller
- Partition by ingest_date (single partition for first run, real pattern in prod)
- Never modify bronze data after write — re-ingest = new partition
"""
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
BRONZE = ROOT / "data" / "bronze"
BRONZE.mkdir(parents=True, exist_ok=True)

# canonical name → source CSV
TABLES = {
    "orders":               "olist_orders_dataset.csv",
    "order_items":          "olist_order_items_dataset.csv",
    "order_payments":       "olist_order_payments_dataset.csv",
    "order_reviews":        "olist_order_reviews_dataset.csv",
    "products":             "olist_products_dataset.csv",
    "sellers":              "olist_sellers_dataset.csv",
    "customers":            "olist_customers_dataset.csv",
    "geolocation":          "olist_geolocation_dataset.csv",
    "category_translation": "product_category_name_translation.csv",
}


def ingest_one(name: str, csv_name: str, ingested_at: datetime) -> None:
    src = RAW / csv_name
    if not src.exists():
        print(f"  SKIP {name}: source CSV not found at {src}")
        return

    df = pl.read_csv(
        src,
        infer_schema_length=10_000,
        ignore_errors=False,
        try_parse_dates=False,
    )
    df = df.with_columns(
        pl.lit(ingested_at).alias("_ingested_at"),
        pl.lit(csv_name).alias("_source_file"),
    )

    out = BRONZE / f"{name}.parquet"
    df.write_parquet(out, compression="snappy")

    rows, cols = df.shape
    size_mb = out.stat().st_size / 1024 / 1024
    print(f"  {name:25s} {rows:>9,} rows  {cols:>2} cols  {size_mb:>7.2f} MB")


def main() -> None:
    ingested_at = datetime.now(timezone.utc)
    print(f"Bronze ingest at {ingested_at.isoformat()}")
    print(f"Source: {RAW}")
    print(f"Target: {BRONZE}")
    print()

    for name, csv in TABLES.items():
        ingest_one(name, csv, ingested_at)


if __name__ == "__main__":
    main()
