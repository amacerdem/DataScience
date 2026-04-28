"""Türkçe doğal dil → SQL → Cevap (Anthropic Claude).

Backend: SQL_BACKEND=mssql (default — Microsoft SQL Server / Azure SQL / Fabric)
         SQL_BACKEND=duckdb (legacy lokal Parquet)

Aynı prompt şeması Power BI Service XMLA endpoint üstünden DAX üretmeye
de uyarlanır — sadece schema.py + dialect değişir.

Kullanım:
    python llm/nl2sql.py "geçen ay en çok satan 5 kategori nedir?"
    python llm/nl2sql.py --interactive
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import textwrap
from pathlib import Path

import anthropic
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))
from llm.schema import SYSTEM_PROMPT, BACKEND  # noqa: E402

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5")
FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|MERGE|GRANT|REVOKE|EXEC|EXECUTE|XP_)\b",
    re.IGNORECASE,
)


def get_connection():
    """Backend-aware connection factory."""
    if BACKEND == "mssql":
        import pymssql
        return pymssql.connect(
            server=os.environ["MSSQL_HOST"],
            port=int(os.environ["MSSQL_PORT"]),
            user=os.environ["MSSQL_USER"],
            password=os.environ["MSSQL_PASSWORD"],
            database=os.environ["MSSQL_DATABASE"],
        )
    if BACKEND == "duckdb":
        import duckdb
        con = duckdb.connect(str(ROOT / "data" / "warehouse.duckdb"), read_only=True)
        con.execute(f"SET file_search_path = '{ROOT}'")
        return con
    raise SystemExit(f"Unknown SQL_BACKEND: {BACKEND}")


def fetch_df(sql: str):
    import pandas as pd
    if BACKEND == "mssql":
        from sqlalchemy import create_engine
        engine = create_engine(
            f"mssql+pymssql://{os.environ['MSSQL_USER']}:{os.environ['MSSQL_PASSWORD']}"
            f"@{os.environ['MSSQL_HOST']}:{os.environ['MSSQL_PORT']}/{os.environ['MSSQL_DATABASE']}"
        )
        with engine.connect() as con:
            return pd.read_sql(sql, con)
    con = get_connection()
    return con.execute(sql).fetchdf()


def generate_sql(question: str) -> str:
    client = anthropic.Anthropic()
    kwargs = dict(
        model=MODEL,
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": question.strip()}],
    )
    if MODEL.startswith("claude-opus-4-7") or MODEL.startswith("claude-opus-4-6"):
        kwargs["thinking"] = {"type": "adaptive"}
        kwargs["output_config"] = {"effort": "high"}
    response = client.messages.create(**kwargs)
    sql = next(b.text for b in response.content if b.type == "text").strip()
    sql = re.sub(r"^```(?:sql|tsql|mssql)?\s*", "", sql)
    sql = re.sub(r"\s*```$", "", sql)
    sql = sql.rstrip(";").strip()
    return sql


def validate(sql: str) -> None:
    if FORBIDDEN.search(sql):
        raise ValueError(f"Reddedildi (yazma/yan etki): {sql[:100]}")
    if not re.match(r"^\s*(WITH|SELECT)", sql, re.IGNORECASE):
        raise ValueError("Sadece SELECT/WITH ile başlayan sorgu kabul edilir.")


def answer(question: str) -> None:
    print(f"\nSORU: {question}")
    print("-" * 70)
    sql = generate_sql(question)
    print(f"ÜRETİLEN SQL ({MODEL} • {BACKEND}):")
    print(textwrap.indent(sql, "  "))
    print()
    try:
        validate(sql)
    except ValueError as e:
        print(f"GÜVENLİK: {e}")
        return
    df = fetch_df(sql)
    if df.empty:
        print("(sonuç yok)")
        return
    print("CEVAP:")
    print(textwrap.indent(df.to_string(index=False), "  "))


def repl() -> None:
    print(f"Model: {MODEL}   Backend: {BACKEND}")
    print("Türkçe soru sor (çıkmak: 'exit'):")
    while True:
        try:
            q = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if q.lower() in {"exit", "quit", "q"}:
            break
        if not q:
            continue
        try:
            answer(q)
        except Exception as e:
            print(f"HATA: {e}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("question", nargs="*", help="Türkçe soru")
    p.add_argument("--interactive", "-i", action="store_true", help="REPL modu")
    args = p.parse_args()
    if args.interactive or not args.question:
        repl()
    else:
        answer(" ".join(args.question))


if __name__ == "__main__":
    main()
