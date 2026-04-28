"""End-to-end orchestrator for the SQL Server pipeline.

  python scripts/run_mssql.py            # full: init → load bronze → silver → gold
  python scripts/run_mssql.py --skip-init  # if schemas/tables already exist
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import re
import sys
import time
from pathlib import Path

import pymssql
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def import_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def split_batches(sql: str) -> list[str]:
    """Split T-SQL by GO statements (case-insensitive, on its own line)."""
    return [b.strip() for b in re.split(r"^\s*GO\s*$", sql, flags=re.IGNORECASE | re.MULTILINE) if b.strip()]


def run_sql(label: str, sql_path: Path, database: str | None = None) -> None:
    print(f"\n=== {label} ===")
    print(f"  {sql_path.relative_to(ROOT)}")
    sql = sql_path.read_text()

    conn_kwargs = dict(
        server=os.environ["MSSQL_HOST"],
        port=int(os.environ["MSSQL_PORT"]),
        user=os.environ["MSSQL_USER"],
        password=os.environ["MSSQL_PASSWORD"],
        autocommit=True,
    )
    if database:
        conn_kwargs["database"] = database

    t0 = time.perf_counter()
    con = pymssql.connect(**conn_kwargs)
    cur = con.cursor()
    for batch in split_batches(sql):
        # PRINT messages and SELECT results — fetch what we can, ignore otherwise
        cur.execute(batch)
        try:
            rows = cur.fetchall()
            if rows and cur.description:
                cols = [d[0] for d in cur.description]
                for r in rows:
                    print("  " + ", ".join(f"{c}={v}" for c, v in zip(cols, r)))
        except pymssql.OperationalError:
            pass

    msgs = getattr(con, "_msg_queue", None)  # pymssql exposes server PRINT via _msg_queue
    con.close()
    print(f"  done in {time.perf_counter() - t0:.2f}s")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--skip-init",  action="store_true", help="skip 01_init.sql")
    p.add_argument("--skip-load",  action="store_true", help="skip Parquet → bronze loader")
    args = p.parse_args()

    if not args.skip_init:
        # 01_init.sql USEs master to CREATE DATABASE; pass database=None
        run_sql("STEP 1: INIT (db, schemas, tables)", ROOT / "sql" / "tsql" / "01_init.sql", database=None)

    if not args.skip_load:
        print("\n=== STEP 2: LOAD BRONZE (Parquet → SQL Server) ===")
        mod = import_module("load_mssql", ROOT / "scripts" / "02_load_mssql.py")
        mod.main()

    run_sql("STEP 3: SILVER (T-SQL transforms)",  ROOT / "sql" / "tsql" / "02_silver.sql", database="olist")
    run_sql("STEP 4: GOLD   (T-SQL star schema)", ROOT / "sql" / "tsql" / "03_gold.sql",   database="olist")

    print("\n=== DONE ===")
    print("Verify with Azure Data Studio (free) or:")
    print("  python -c \"import os,pymssql; c=pymssql.connect('localhost','sa',os.environ['MSSQL_PASSWORD'],'olist'); cur=c.cursor(); cur.execute('SELECT TOP 5 * FROM gold.DimGeography'); [print(r) for r in cur.fetchall()]\"")


if __name__ == "__main__":
    main()
