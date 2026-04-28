"""Execute a SQL file against the project's DuckDB warehouse.

Usage:
    python scripts/run_sql.py sql/02_silver.sql
    python scripts/run_sql.py sql/03_gold.sql
"""
import sys
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "warehouse.duckdb"


def main(sql_path: str) -> None:
    sql_file = Path(sql_path)
    if not sql_file.is_absolute():
        sql_file = ROOT / sql_file

    print(f"DB:  {DB}")
    print(f"SQL: {sql_file}")
    sql = sql_file.read_text()

    con = duckdb.connect(str(DB))
    con.execute(f"SET file_search_path = '{ROOT}'")

    t0 = time.perf_counter()
    # DuckDB's execute() handles multi-statement SQL natively
    result = con.execute(sql)
    try:
        rows = result.fetchall()
        if rows:
            cols = [d[0] for d in result.description]
            print("\n" + " | ".join(cols))
            print("-" * 60)
            for r in rows:
                print(" | ".join(str(v) for v in r))
    except Exception:
        pass
    elapsed = time.perf_counter() - t0
    print(f"\nDone in {elapsed:.2f}s")
    con.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1])
