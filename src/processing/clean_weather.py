from __future__ import annotations

import re

import pandas as pd

from src import config
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


def _find_hourly_header(path) -> int:
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        for idx, line in enumerate(f):
            if line.lower().startswith("time,"):
                return idx
    return 0


def _standardize_col(col: str) -> str:
    text = col.strip().lower()
    text = re.sub(r"\s*\(.*?\)", "", text)
    text = text.replace("Â", "")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


def clean_weather() -> None:
    config.ensure_directories()
    skiprows = _find_hourly_header(config.WEATHER_DATA_PATH)
    weather = pd.read_csv(config.WEATHER_DATA_PATH, skiprows=skiprows)
    weather.columns = [_standardize_col(col) for col in weather.columns]
    if "time" not in weather.columns:
        raise ValueError(f"Unable to find hourly time column in {config.WEATHER_DATA_PATH}")
    weather["weather_hour"] = pd.to_datetime(weather["time"], errors="coerce").dt.floor("h")
    for col in weather.columns:
        if col not in {"time", "weather_hour"}:
            weather[col] = pd.to_numeric(weather[col], errors="coerce")
    keep = [
        "weather_hour",
        "temperature_2m",
        "relative_humidity_2m",
        "precipitation",
        "rain",
        "snowfall",
        "weather_code",
        "wind_speed_10m",
    ]
    for col in keep:
        if col not in weather:
            weather[col] = pd.NA
    weather = weather[keep].drop_duplicates(subset=["weather_hour"]).sort_values("weather_hour")
    weather.to_parquet(config.CLEANED_WEATHER_PARQUET, index=False)
    logger.info("Wrote %s weather rows to %s", len(weather), config.CLEANED_WEATHER_PARQUET)


if __name__ == "__main__":
    clean_weather()
