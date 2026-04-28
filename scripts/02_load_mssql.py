"""Load bronze Parquet files into SQL Server bronze.* tables.

This is the "ingestion" step in the Microsoft pattern: Python (or ADF /
Fabric Pipelines / SSIS in production) pulls raw data, lands it in
bronze tables. Everything downstream (silver, gold) is pure T-SQL.

Idempotent: TRUNCATEs each bronze table before insert.

    python scripts/02_load_mssql.py
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import polars as pl
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
BRONZE = ROOT / "data" / "bronze"

# canonical name → (parquet file, source CSV name to log)
TABLES = [
    ("orders",               "olist_orders_dataset.csv"),
    ("order_items",          "olist_order_items_dataset.csv"),
    ("order_payments",       "olist_order_payments_dataset.csv"),
    ("order_reviews",        "olist_order_reviews_dataset.csv"),
    ("products",             "olist_products_dataset.csv"),
    ("sellers",              "olist_sellers_dataset.csv"),
    ("customers",            "olist_customers_dataset.csv"),
    ("geolocation",          "olist_geolocation_dataset.csv"),
    ("category_translation", "product_category_name_translation.csv"),
]

# Bronze column order — matches sql/tsql/01_init.sql DDL exactly.
# _ingested_at is server-side default (SYSUTCDATETIME); we only insert _source_file.
COLUMNS = {
    "orders": [
        "order_id", "customer_id", "order_status",
        "order_purchase_timestamp", "order_approved_at",
        "order_delivered_carrier_date", "order_delivered_customer_date",
        "order_estimated_delivery_date", "_source_file",
    ],
    "order_items": [
        "order_id", "order_item_id", "product_id", "seller_id",
        "shipping_limit_date", "price", "freight_value", "_source_file",
    ],
    "order_payments": [
        "order_id", "payment_sequential", "payment_type",
        "payment_installments", "payment_value", "_source_file",
    ],
    "order_reviews": [
        "review_id", "order_id", "review_score",
        "review_comment_title", "review_comment_message",
        "review_creation_date", "review_answer_timestamp", "_source_file",
    ],
    "products": [
        "product_id", "product_category_name",
        "product_name_lenght", "product_description_lenght", "product_photos_qty",
        "product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm",
        "_source_file",
    ],
    "sellers": [
        "seller_id", "seller_zip_code_prefix", "seller_city", "seller_state",
        "_source_file",
    ],
    "customers": [
        "customer_id", "customer_unique_id", "customer_zip_code_prefix",
        "customer_city", "customer_state", "_source_file",
    ],
    "geolocation": [
        "geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng",
        "geolocation_city", "geolocation_state", "_source_file",
    ],
    "category_translation": [
        "product_category_name", "product_category_name_english", "_source_file",
    ],
}

CHUNK = 10_000  # rows per executemany batch — tune up for faster, down for less memory


def get_engine():
    user = os.environ["MSSQL_USER"]
    pwd  = os.environ["MSSQL_PASSWORD"]
    host = os.environ["MSSQL_HOST"]
    port = os.environ["MSSQL_PORT"]
    db   = os.environ["MSSQL_DATABASE"]
    return create_engine(f"mssql+pymssql://{user}:{pwd}@{host}:{port}/{db}")


def load_one(engine, name: str, csv_name: str) -> tuple[int, float]:
    src = BRONZE / f"{name}.parquet"
    if not src.exists():
        print(f"  SKIP {name}: not found at {src}")
        return 0, 0.0

    df = pl.read_parquet(src).drop("_ingested_at", strict=False)
    if "_source_file" not in df.columns:
        df = df.with_columns(pl.lit(csv_name).alias("_source_file"))

    cols = COLUMNS[name]
    df = df.select([c for c in cols if c in df.columns])

    pdf = df.to_pandas()

    t0 = time.perf_counter()
    with engine.begin() as con:
        con.execute(text(f"TRUNCATE TABLE bronze.{name}"))
        pdf.to_sql(
            name,
            con,
            schema="bronze",
            if_exists="append",
            index=False,
            chunksize=CHUNK,
            method=None,
        )
    elapsed = time.perf_counter() - t0
    return len(pdf), elapsed


def main() -> None:
    engine = get_engine()
    print(f"Loading bronze → SQL Server ({os.environ['MSSQL_HOST']}:{os.environ['MSSQL_PORT']}/{os.environ['MSSQL_DATABASE']})")
    print()
    total_rows = 0
    total_time = 0.0
    for name, csv in TABLES:
        rows, secs = load_one(engine, name, csv)
        total_rows += rows
        total_time += secs
        print(f"  {name:25s} {rows:>9,} rows  in {secs:>5.2f}s")
    print()
    print(f"Total: {total_rows:,} rows in {total_time:.1f}s")


if __name__ == "__main__":
    main()
