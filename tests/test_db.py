"""SQL Server connectivity smoke tests (require running container)."""
import pytest
from api.db import fetch_df, get_connection


@pytest.mark.integration
def test_connection_returns_version():
    with get_connection() as con:
        cur = con.cursor()
        cur.execute("SELECT @@VERSION")
        row = cur.fetchone()
        assert row is not None
        assert "SQL" in row[0]


@pytest.mark.integration
def test_fetch_df_returns_pandas():
    df = fetch_df("SELECT 1 AS x, 'hello' AS y")
    assert df.shape == (1, 2)
    assert list(df.columns) == ["x", "y"]
    assert df.iloc[0]["x"] == 1
