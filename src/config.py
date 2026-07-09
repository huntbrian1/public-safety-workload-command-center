from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except Exception:
    # The pipeline can still run with environment variables/defaults if
    # python-dotenv is not available, but full production runs should install it.
    pass


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
EXTERNAL_DIR = DATA_DIR / "external"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"

OUTPUT_DIR = PROJECT_ROOT / "outputs"
SQL_OUTPUT_DIR = OUTPUT_DIR / "sql"
HEX_OUTPUT_DIR = OUTPUT_DIR / "hex"
TABLEAU_OUTPUT_DIR = OUTPUT_DIR / "tableau"
EXCEL_OUTPUT_DIR = OUTPUT_DIR / "excel"
MODEL_OUTPUT_DIR = OUTPUT_DIR / "models"
MEMO_OUTPUT_DIR = OUTPUT_DIR / "memo"
CHART_OUTPUT_DIR = OUTPUT_DIR / "charts"

CALL_DATA_PATH = RAW_DIR / "seattle_call_data_full.csv"
WEATHER_DATA_PATH = EXTERNAL_DIR / "seattle_weather_hourly_2021_2025.csv"
BEATS_CSV_PATH = EXTERNAL_DIR / "seattle_police_beats.csv"
BEATS_GEOJSON_PATH = EXTERNAL_DIR / "seattle_police_beats.geojson"

CLEANED_CALLS_PARQUET = INTERIM_DIR / "cleaned_call_events.parquet"
CLEANED_CALLS_PREVIEW = INTERIM_DIR / "cleaned_call_events_preview.csv"
CLEANED_WEATHER_PARQUET = INTERIM_DIR / "cleaned_weather_hourly.parquet"
CLEANED_BEATS_CSV = INTERIM_DIR / "cleaned_police_beats.csv"

FACT_EVENTS_PARQUET = PROCESSED_DIR / "fact_service_events.parquet"
FACT_EVENTS_SAMPLE_CSV = PROCESSED_DIR / "fact_service_events_sample.csv"
ZONE_HOUR_FEATURES_PARQUET = PROCESSED_DIR / "zone_hour_features.parquet"
ZONE_HOUR_FEATURES_CSV = PROCESSED_DIR / "zone_hour_features.csv"

SQLITE_DB_PATH = PROJECT_ROOT / os.getenv("SQLITE_DB_PATH", "data/processed/public_safety_ops.sqlite")

SAMPLE_MODE = _bool_env("SAMPLE_MODE", True)
_sample_rows_raw = os.getenv("SAMPLE_ROWS", "500000").strip()
SAMPLE_ROWS = int(_sample_rows_raw) if _sample_rows_raw else None
RANDOM_SEED = int(os.getenv("RANDOM_SEED", "42"))
DATE_START = os.getenv("DATE_START", "2021-01-01")
DATE_END = os.getenv("DATE_END", "2025-12-31")
LOCAL_TIMEZONE = os.getenv("LOCAL_TIMEZONE", "America/Los_Angeles")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "public_safety_ops")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "raw_call_events")

REQUIRED_FILES = {
    "call_data": CALL_DATA_PATH,
    "weather_hourly": WEATHER_DATA_PATH,
    "beat_lookup": BEATS_CSV_PATH,
    "beat_geojson": BEATS_GEOJSON_PATH,
}


def ensure_directories() -> None:
    for path in [
        RAW_DIR,
        EXTERNAL_DIR,
        INTERIM_DIR,
        PROCESSED_DIR,
        SQL_OUTPUT_DIR,
        HEX_OUTPUT_DIR,
        TABLEAU_OUTPUT_DIR,
        EXCEL_OUTPUT_DIR,
        MODEL_OUTPUT_DIR,
        MEMO_OUTPUT_DIR,
        CHART_OUTPUT_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)
