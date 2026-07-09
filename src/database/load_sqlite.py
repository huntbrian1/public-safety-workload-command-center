from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

from src import config
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


def _bool_to_int(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if out[col].dtype == bool:
            out[col] = out[col].astype("int8")
    return out


def _stringify_datetimes(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            out[col] = out[col].dt.strftime("%Y-%m-%d %H:%M:%S")
        elif pd.api.types.is_object_dtype(out[col]):
            # Date objects from pyarrow arrive as object dtype; stringify them for SQLite portability.
            sample = out[col].dropna().head(1)
            if not sample.empty and hasattr(sample.iloc[0], "isoformat"):
                out[col] = out[col].map(lambda x: x.isoformat() if hasattr(x, "isoformat") else x)
    return out


def _load_parquet_dataset_to_sqlite(path: Path, table: str, conn: sqlite3.Connection, batch_size: int = 100_000) -> int:
    import pyarrow.dataset as ds

    dataset = ds.dataset(path, format="parquet")
    total = 0
    first = True
    for batch in dataset.to_batches(batch_size=batch_size):
        df = batch.to_pandas()
        df = _stringify_datetimes(_bool_to_int(df))
        df.to_sql(table, conn, if_exists="replace" if first else "append", index=False, chunksize=500, method="multi")
        total += len(df)
        first = False
        logger.info("Loaded %s rows into %s", f"{total:,}", table)
    if first:
        pd.DataFrame().to_sql(table, conn, if_exists="replace", index=False)
    return total


def _load_optional_csv(csv_path: Path, table: str, conn: sqlite3.Connection) -> int:
    if not csv_path.exists():
        return 0
    df = pd.read_csv(csv_path)
    df = _stringify_datetimes(_bool_to_int(df))
    df.to_sql(table, conn, if_exists="replace", index=False)
    return len(df)


def load_sqlite() -> None:
    config.ensure_directories()
    started = datetime.now()
    if not config.FACT_EVENTS_PARQUET.exists():
        raise FileNotFoundError(config.FACT_EVENTS_PARQUET)
    if not config.ZONE_HOUR_FEATURES_PARQUET.exists():
        raise FileNotFoundError(config.ZONE_HOUR_FEATURES_PARQUET)

    if config.SQLITE_DB_PATH.exists():
        config.SQLITE_DB_PATH.unlink()

    conn = sqlite3.connect(config.SQLITE_DB_PATH)
    row_counts: dict[str, int] = {}
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA temp_store=MEMORY")

        row_counts["fact_service_events"] = _load_parquet_dataset_to_sqlite(config.FACT_EVENTS_PARQUET, "fact_service_events", conn)
        row_counts["zone_hour_features"] = _load_parquet_dataset_to_sqlite(config.ZONE_HOUR_FEATURES_PARQUET, "zone_hour_features", conn)

        dim_sql = {
            "dim_date": """
                CREATE TABLE dim_date AS
                SELECT DISTINCT event_date, weekday, weekday_name, month, month_name, quarter, year, season, is_weekend, is_holiday
                FROM fact_service_events
            """,
            "dim_location": """
                CREATE TABLE dim_location AS
                SELECT DISTINCT zone_id, beat, sector, precinct, latitude, longitude
                FROM fact_service_events
            """,
            "dim_service_category": """
                CREATE TABLE dim_service_category AS
                SELECT DISTINCT normalized_service_category
                FROM fact_service_events
            """,
            "dim_weather_hour": """
                CREATE TABLE dim_weather_hour AS
                SELECT DISTINCT weather_hour, temperature_2m, relative_humidity_2m, precipitation, rain, snowfall, weather_code, wind_speed_10m
                FROM fact_service_events
            """,
        }
        for table, sql in dim_sql.items():
            conn.execute(f"DROP TABLE IF EXISTS {table}")
            conn.execute(sql)
            row_counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

        optional = [
            (config.HEX_OUTPUT_DIR / "hex_cluster_profiles.csv", "cluster_profiles"),
            (config.HEX_OUTPUT_DIR / "hex_model_predictions.csv", "model_predictions"),
            (config.HEX_OUTPUT_DIR / "hex_recommendations.csv", "product_service_recommendations"),
        ]
        for csv_path, table in optional:
            loaded = _load_optional_csv(csv_path, table, conn)
            if loaded:
                row_counts[table] = loaded

        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_fact_date ON fact_service_events(event_date)",
            "CREATE INDEX IF NOT EXISTS idx_fact_hour ON fact_service_events(event_hour)",
            "CREATE INDEX IF NOT EXISTS idx_fact_zone ON fact_service_events(zone_id)",
            "CREATE INDEX IF NOT EXISTS idx_fact_category ON fact_service_events(normalized_service_category)",
            "CREATE INDEX IF NOT EXISTS idx_zone_hour_zone ON zone_hour_features(zone_id)",
            "CREATE INDEX IF NOT EXISTS idx_zone_hour_date_hour ON zone_hour_features(date_hour)",
        ]
        for stmt in indexes:
            conn.execute(stmt)
        conn.commit()
    finally:
        conn.close()

    ended = datetime.now()
    lines = [
        "# SQLite Load Report",
        "",
        f"- Run mode full: `{not config.SAMPLE_MODE}`",
        f"- Started: `{started.isoformat(timespec='seconds')}`",
        f"- Ended: `{ended.isoformat(timespec='seconds')}`",
        f"- Elapsed seconds: `{(ended - started).total_seconds():,.1f}`",
        f"- Database path: `{config.SQLITE_DB_PATH}`",
        f"- Database size bytes: `{config.SQLITE_DB_PATH.stat().st_size if config.SQLITE_DB_PATH.exists() else 0:,}`",
        "",
        "| Table | Rows |",
        "|---|---:|",
    ]
    lines.extend(f"| {table} | {rows:,} |" for table, rows in row_counts.items())
    (config.MEMO_OUTPUT_DIR / "sqlite_load_report.md").write_text("\n".join(lines), encoding="utf-8")
    logger.info("SQLite database loaded at %s", config.SQLITE_DB_PATH)


if __name__ == "__main__":
    load_sqlite()
