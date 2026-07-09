from __future__ import annotations

import re
import sqlite3

import pandas as pd

from src import config
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


def _parse_queries(sql_text: str) -> dict[str, str]:
    parts = re.split(r"--\s*name:\s*([a-zA-Z0-9_]+)\s*", sql_text)
    queries = {}
    for idx in range(1, len(parts), 2):
        name = parts[idx].strip()
        sql = parts[idx + 1].strip().rstrip(";")
        if sql:
            queries[name] = sql
    return queries


def run_queries() -> None:
    config.ensure_directories()
    sql_path = config.PROJECT_ROOT / "src" / "database" / "sqlite_analytics_queries.sql"
    queries = _parse_queries(sql_path.read_text(encoding="utf-8"))
    conn = sqlite3.connect(config.SQLITE_DB_PATH)
    lines = ["# SQLite Query Export Report", ""]
    try:
        for name, sql in queries.items():
            try:
                df = pd.read_sql_query(sql, conn)
                out_path = config.SQL_OUTPUT_DIR / f"{name}.csv"
                df.to_csv(out_path, index=False)
                lines.append(f"- `{name}`: {len(df):,} rows -> `{out_path}`")
                logger.info("Exported %s rows for query %s", len(df), name)
            except Exception as exc:
                lines.append(f"- `{name}`: failed with `{exc}`")
                logger.warning("Query %s failed: %s", name, exc)
    finally:
        conn.close()
    (config.MEMO_OUTPUT_DIR / "sqlite_query_export_report.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    run_queries()
