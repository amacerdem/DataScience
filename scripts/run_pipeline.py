"""End-to-end pipeline orchestrator.

Runs the full medallion flow: download → bronze → silver → gold.
Idempotent: re-running rebuilds from the latest raw CSVs.

    python scripts/run_pipeline.py
    python scripts/run_pipeline.py --skip-download   # if data/raw/ already populated
"""
import argparse
import importlib.util
import sys
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]


def import_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def run_sql(label: str, sql_path: Path) -> None:
    print(f"\n=== {label} ===")
    print(f"  {sql_path.name}")
    sql = sql_path.read_text()
    con = duckdb.connect(str(ROOT / "data" / "warehouse.duckdb"))
    con.execute(f"SET file_search_path = '{ROOT}'")
    t0 = time.perf_counter()
    result = con.execute(sql)
    try:
        rows = result.fetchall()
        if rows:
            cols = [d[0] for d in result.description]
            for r in rows:
                print("  " + ", ".join(f"{c}={v}" for c, v in zip(cols, r)))
    except Exception:
        pass
    print(f"  done in {time.perf_counter() - t0:.2f}s")
    con.close()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--skip-download", action="store_true")
    args = p.parse_args()

    if not args.skip_download:
        print("\n=== STEP 0: DOWNLOAD ===")
        mod = import_module("download", ROOT / "scripts" / "00_download.py")
        mod.main()

    print("\n=== STEP 1: BRONZE ===")
    mod = import_module("bronze", ROOT / "scripts" / "01_bronze.py")
    mod.main()

    run_sql("STEP 2: SILVER", ROOT / "sql" / "02_silver.sql")
    run_sql("STEP 3: GOLD",   ROOT / "sql" / "03_gold.sql")

    print("\n=== DONE ===")
    print("Next:")
    print("  • Open Power BI Desktop, follow powerbi/MODEL.md (Get Data → Folder → data/gold/)")
    print("  • Paste DAX from powerbi/MEASURES.dax")
    print("  • Build the 3 dashboards from powerbi/DASHBOARDS.md")
    print("  • For NL→SQL demo:  python llm/nl2sql.py --interactive")


if __name__ == "__main__":
    main()
