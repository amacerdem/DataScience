"""SQL Server connection helpers."""
from contextlib import contextmanager
from typing import Iterator

import pandas as pd
import pymssql
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from api.config import get_settings


@contextmanager
def get_connection() -> Iterator[pymssql.Connection]:
    s = get_settings()
    con = pymssql.connect(
        server=s.mssql_host,
        port=s.mssql_port,
        user=s.mssql_user,
        password=s.mssql_password,
        database=s.mssql_database,
    )
    try:
        yield con
    finally:
        con.close()


_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        s = get_settings()
        _engine = create_engine(
            f"mssql+pymssql://{s.mssql_user}:{s.mssql_password}"
            f"@{s.mssql_host}:{s.mssql_port}/{s.mssql_database}",
            pool_size=5,
            pool_pre_ping=True,
        )
    return _engine


def fetch_df(sql: str) -> pd.DataFrame:
    with get_engine().connect() as con:
        return pd.read_sql(sql, con)
