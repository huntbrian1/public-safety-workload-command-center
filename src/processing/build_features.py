from __future__ import annotations

import numpy as np
import pandas as pd

from src import config
from src.processing.build_calendar_features import add_calendar_features
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


WEATHER_COLS = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "rain",
    "snowfall",
    "weather_code",
    "wind_speed_10m",
]


def _read_required(path):
    if not path.exists():
        raise FileNotFoundError(f"Required processed file is missing: {path}")
    return pd.read_parquet(path)


def _join_weather(fact: pd.DataFrame, weather: pd.DataFrame) -> pd.DataFrame:
    fact = fact.copy()
    weather = weather.copy()
    fact["weather_hour"] = pd.to_datetime(fact["event_datetime"], errors="coerce").dt.floor("h")
    weather["weather_hour"] = pd.to_datetime(weather["weather_hour"], errors="coerce").dt.floor("h")
    joined = fact.merge(weather, on="weather_hour", how="left")
    coverage = joined["temperature_2m"].notna().mean() if "temperature_2m" in joined else 0
    lines = [
        "# Weather Join Quality",
        "",
        f"- Event rows evaluated: `{len(joined):,}`",
        f"- Hourly weather rows: `{len(weather):,}`",
        f"- Exact hour join coverage: `{coverage:.2%}`",
        "",
        "Fallback note: because the Seattle weather file is hourly and local-time based, the primary join rounds service-event timestamps to the nearest lower hour. If exact hourly coverage is low, inspect timezone assumptions and timestamp parsing.",
    ]
    (config.MEMO_OUTPUT_DIR / "weather_join_quality.md").write_text("\n".join(lines), encoding="utf-8")
    return joined


def _category_mix(fact: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    counts = (
        fact.groupby(group_cols + ["normalized_service_category"], dropna=False)
        .size()
        .reset_index(name="category_count")
    )
    totals = counts.groupby(group_cols, dropna=False)["category_count"].sum().reset_index(name="total_count")
    counts = counts.merge(totals, on=group_cols, how="left")
    counts["category_share"] = counts["category_count"] / counts["total_count"].replace(0, np.nan)
    counts = counts.sort_values(group_cols + ["category_share"], ascending=[True] * len(group_cols) + [False])

    top1 = counts.groupby(group_cols, dropna=False).head(1).groupby(group_cols, dropna=False)["category_share"].sum().reset_index(name="category_mix_top_1_share")
    top3 = counts.groupby(group_cols, dropna=False).head(3).groupby(group_cols, dropna=False)["category_share"].sum().reset_index(name="category_mix_top_3_share")
    return top1.merge(top3, on=group_cols, how="outer")


def _add_lag_features(zone_hour: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for _, sub in zone_hour.sort_values(["zone_id", "date_hour"]).groupby("zone_id", dropna=False):
        sub = sub.copy()
        sub["lag_1_hour_demand"] = sub["target_demand_count"].shift(1)
        sub["lag_24_hour_demand"] = sub["target_demand_count"].shift(24)
        sub["rolling_7_day_avg"] = sub["target_demand_count"].shift(1).rolling(window=168, min_periods=1).mean()
        sub["prior_week_same_hour_demand"] = sub["target_demand_count"].shift(168)
        threshold = sub["target_demand_count"].quantile(0.75)
        sub["high_demand_flag"] = (sub["target_demand_count"] > threshold).astype(int)
        frames.append(sub)
    out = pd.concat(frames, ignore_index=True) if frames else zone_hour
    for col in ["lag_1_hour_demand", "lag_24_hour_demand", "rolling_7_day_avg", "prior_week_same_hour_demand"]:
        out[col] = out[col].fillna(0)
    return out


def build_features() -> None:
    config.ensure_directories()
    if not config.SAMPLE_MODE and config.FACT_EVENTS_PARQUET.exists() and config.ZONE_HOUR_FEATURES_PARQUET.exists() and config.ZONE_HOUR_FEATURES_CSV.exists():
        try:
            import pyarrow.dataset as ds

            fact_rows = ds.dataset(config.FACT_EVENTS_PARQUET, format="parquet").count_rows()
            zone_hour_rows = ds.dataset(config.ZONE_HOUR_FEATURES_PARQUET, format="parquet").count_rows()
        except Exception:
            fact_rows = "unknown"
            zone_hour_rows = "unknown"
        lines = [
            "# Build Features Report",
            "",
            "- Run mode: `full`",
            "- Full-mode feature build delegated to `src.processing.spark_transform` to avoid loading the full event fact table into pandas.",
            f"- Fact rows available: `{fact_rows}`",
            f"- Zone-hour rows available: `{zone_hour_rows}`",
            f"- Fact output: `{config.FACT_EVENTS_PARQUET}`",
            f"- Zone-hour output: `{config.ZONE_HOUR_FEATURES_PARQUET}`",
            f"- Zone-hour CSV: `{config.ZONE_HOUR_FEATURES_CSV}`",
        ]
        (config.MEMO_OUTPUT_DIR / "build_features_report.md").write_text("\n".join(lines), encoding="utf-8")
        logger.info("Full-mode Spark feature outputs verified; skipping pandas rebuild.")
        return

    calls = _read_required(config.CLEANED_CALLS_PARQUET)
    weather = _read_required(config.CLEANED_WEATHER_PARQUET)
    geography = pd.read_csv(config.CLEANED_BEATS_CSV) if config.CLEANED_BEATS_CSV.exists() else pd.DataFrame()

    fact = add_calendar_features(calls, "event_datetime")
    fact = _join_weather(fact, weather)
    if not geography.empty and "zone_id" in geography:
        geo_cols = [c for c in ["zone_id", "precinct", "sector"] if c in geography]
        geo = geography[geo_cols].drop_duplicates("zone_id")
        fact = fact.merge(geo, on="zone_id", how="left", suffixes=("", "_geo"))
        fact["precinct"] = fact.get("precinct").fillna(fact.get("precinct_geo")) if "precinct_geo" in fact else fact.get("precinct")
        fact["sector"] = fact.get("sector").fillna(fact.get("sector_geo")) if "sector_geo" in fact else fact.get("sector")

    fact["demand_count"] = 1
    fact["zone_id"] = fact["zone_id"].fillna("UNKNOWN")
    fact["beat"] = fact.get("beat", fact["zone_id"]).fillna(fact["zone_id"])
    for col in WEATHER_COLS:
        if col not in fact:
            fact[col] = pd.NA

    fact_cols = [
        "event_id",
        "event_datetime",
        "weather_hour",
        "event_date",
        "event_hour",
        "weekday",
        "weekday_name",
        "month",
        "month_name",
        "quarter",
        "year",
        "season",
        "is_weekend",
        "is_holiday",
        "is_business_hour",
        "is_after_hours",
        "zone_id",
        "beat",
        "sector",
        "precinct",
        "latitude",
        "longitude",
        "initial_call_type",
        "final_call_type",
        "normalized_service_category",
        "disposition",
        *WEATHER_COLS,
        "data_quality_flag",
        "demand_count",
    ]
    for col in fact_cols:
        if col not in fact:
            fact[col] = pd.NA
    fact = fact[fact_cols]
    fact.to_parquet(config.FACT_EVENTS_PARQUET, index=False)
    fact.head(50_000).to_csv(config.FACT_EVENTS_SAMPLE_CSV, index=False)
    logger.info("Wrote fact table with %s rows", len(fact))

    group_cols = [
        "zone_id",
        "event_date",
        "event_hour",
        "weekday",
        "month",
        "quarter",
        "is_weekend",
        "is_holiday",
        "is_business_hour",
        "is_after_hours",
    ]
    agg = fact.groupby(group_cols, dropna=False).agg(
        target_demand_count=("demand_count", "sum"),
        temperature_2m=("temperature_2m", "mean"),
        relative_humidity_2m=("relative_humidity_2m", "mean"),
        precipitation=("precipitation", "mean"),
        rain=("rain", "mean"),
        snowfall=("snowfall", "mean"),
        weather_code=("weather_code", "first"),
        wind_speed_10m=("wind_speed_10m", "mean"),
    ).reset_index()
    mix = _category_mix(fact, group_cols)
    zone_hour = agg.merge(mix, on=group_cols, how="left")
    zone_hour["date"] = pd.to_datetime(zone_hour["event_date"])
    zone_hour["hour"] = zone_hour["event_hour"].astype(int)
    zone_hour["date_hour"] = zone_hour["date"] + pd.to_timedelta(zone_hour["hour"], unit="h")
    zone_hour = _add_lag_features(zone_hour)
    final_cols = [
        "zone_id",
        "date",
        "date_hour",
        "hour",
        "weekday",
        "month",
        "quarter",
        "is_weekend",
        "is_holiday",
        "is_business_hour",
        "is_after_hours",
        *WEATHER_COLS,
        "lag_1_hour_demand",
        "lag_24_hour_demand",
        "rolling_7_day_avg",
        "prior_week_same_hour_demand",
        "category_mix_top_1_share",
        "category_mix_top_3_share",
        "target_demand_count",
        "high_demand_flag",
    ]
    zone_hour = zone_hour[final_cols]
    zone_hour.to_parquet(config.ZONE_HOUR_FEATURES_PARQUET, index=False)
    zone_hour.to_csv(config.ZONE_HOUR_FEATURES_CSV, index=False)
    logger.info("Wrote zone-hour feature table with %s rows", len(zone_hour))


if __name__ == "__main__":
    build_features()
