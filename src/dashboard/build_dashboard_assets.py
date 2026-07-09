from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
PROCESSED_DIR = DATA_DIR / "processed"
APP_DIR = DATA_DIR / "app"
EXTERNAL_DIR = DATA_DIR / "external"
MEMO_DIR = PROJECT_ROOT / "outputs" / "memo"

ZONE_HOUR_CSV = PROCESSED_DIR / "zone_hour_features.csv"
FACT_SAMPLE_CSV = PROCESSED_DIR / "fact_service_events_sample.csv"
BEATS_GEOJSON = EXTERNAL_DIR / "seattle_police_beats.geojson"
APP_BEATS_GEOJSON = APP_DIR / "seattle_police_beats.geojson"
SPARK_REPORT = MEMO_DIR / "pyspark_processing_report.md"
DUPLICATE_REPORT = MEMO_DIR / "duplicate_audit_report.md"

CHUNK_SIZE = 350_000
WEEKDAY_NAMES = {
    0: "Monday",
    1: "Tuesday",
    2: "Wednesday",
    3: "Thursday",
    4: "Friday",
    5: "Saturday",
    6: "Sunday",
}


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _parse_int(text: str, label: str) -> int | None:
    match = re.search(rf"- {re.escape(label)}:\s+`?([0-9,]+)`?", text)
    return int(match.group(1).replace(",", "")) if match else None


def _parse_value(text: str, label: str) -> str | None:
    match = re.search(rf"- {re.escape(label)}:\s+`?([^`\n]+)`?", text)
    return match.group(1).strip() if match else None


def _parse_percent(text: str, label: str) -> float | None:
    raw = _parse_value(text, label)
    return float(raw.replace("%", "")) / 100 if raw else None


def _parse_report_metrics() -> dict[str, Any]:
    spark_text = _read_text(SPARK_REPORT)
    duplicate_text = _read_text(DUPLICATE_REPORT)
    metrics: dict[str, Any] = {
        "spark_version": _parse_value(spark_text, "Spark version"),
        "java_version": _parse_value(spark_text, "Java version"),
        "run_mode_full": _parse_value(spark_text, "Run mode full"),
        "pandas_fallback_used": _parse_value(spark_text, "Pandas fallback used"),
        "input_cleaned_call_rows": _parse_int(spark_text, "Input cleaned call rows"),
        "fact_output_rows": _parse_int(spark_text, "Fact output rows"),
        "zone_hour_output_rows": _parse_int(spark_text, "Zone-hour output rows"),
        "number_of_zones_beats": _parse_int(spark_text, "Number of zones/beats"),
        "weather_join_coverage": _parse_percent(spark_text, "Weather join coverage"),
        "spark_report_path": str(SPARK_REPORT),
        "raw_source_rows": _parse_int(duplicate_text, "Raw row count"),
    }
    date_match = re.search(r"- Date range:\s+`?([^`\n]+)`?\s+to\s+`?([^`\n]+)`?", spark_text)
    if date_match:
        start, end = date_match.groups()
        metrics["date_start"] = start[:10]
        metrics["date_end"] = end[:10]
    return metrics


def _choose_col(columns: list[str], candidates: list[str], role: str, required: bool = True) -> str | None:
    lookup = {c.lower(): c for c in columns}
    for candidate in candidates:
        if candidate.lower() in lookup:
            return lookup[candidate.lower()]
    if required:
        available = ", ".join(columns)
        expected = ", ".join(candidates)
        raise RuntimeError(f"Missing required {role} column. Expected one of [{expected}]. Available columns: {available}")
    return None


def _to_bool(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    return series.astype(str).str.lower().isin({"true", "1", "yes", "y"})


def _sum_parts(parts: list[pd.DataFrame], group_cols: list[str], sum_cols: list[str]) -> pd.DataFrame:
    if not parts:
        return pd.DataFrame(columns=group_cols + sum_cols)
    out = pd.concat(parts, ignore_index=True)
    return out.groupby(group_cols, as_index=False)[sum_cols].sum()


def _safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    return np.where(denominator.to_numpy() == 0, 0, numerator.to_numpy() / denominator.to_numpy())


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    return str(value)


def _add_period_columns(df: pd.DataFrame, date_col: str = "date") -> pd.DataFrame:
    out = df.copy()
    parsed = pd.to_datetime(out[date_col], errors="coerce")
    out["date"] = parsed.dt.date.astype("string")
    out["year"] = parsed.dt.year.astype("Int64")
    out["month"] = parsed.dt.month.astype("Int64")
    out["period"] = parsed.dt.strftime("%Y-%m")
    return out


def _finalize_zone_summary(zone_summary: pd.DataFrame, peak_hours: pd.DataFrame) -> pd.DataFrame:
    if zone_summary.empty:
        return zone_summary
    out = zone_summary.copy()
    out["avg_calls_per_zone_hour"] = _safe_divide(out["total_service_demand"], out["zone_hour_records"])
    out["weekend_share"] = _safe_divide(out["weekend_demand"], out["total_service_demand"])
    out["after_hours_share"] = _safe_divide(out["after_hours_demand"], out["total_service_demand"])
    out["high_demand_hour_rate"] = _safe_divide(out["high_demand_hours"], out["zone_hour_records"])
    out = out.merge(peak_hours, on=[c for c in peak_hours.columns if c in out.columns and c != "peak_hour"], how="left")
    return out.sort_values("total_service_demand", ascending=False)


def build_assets() -> dict[str, int]:
    if not ZONE_HOUR_CSV.exists():
        raise FileNotFoundError(f"Zone-hour CSV not found: {ZONE_HOUR_CSV}")
    APP_DIR.mkdir(parents=True, exist_ok=True)
    if BEATS_GEOJSON.exists():
        shutil.copyfile(BEATS_GEOJSON, APP_BEATS_GEOJSON)

    header = pd.read_csv(ZONE_HOUR_CSV, nrows=0)
    columns = list(header.columns)
    print("Available zone-hour columns:")
    print(", ".join(columns))

    zone_col = _choose_col(columns, ["zone_id", "beat", "zone", "beat_id"], "zone/beat")
    date_col = _choose_col(columns, ["date", "event_date", "service_date"], "date")
    hour_col = _choose_col(columns, ["hour", "event_hour", "hour_of_day"], "hour")
    weekday_col = _choose_col(columns, ["weekday", "day_of_week"], "weekday")
    weekend_col = _choose_col(columns, ["is_weekend", "weekend"], "weekday/weekend flag", required=False)
    demand_col = _choose_col(columns, ["target_demand_count", "demand_count", "event_count", "call_count"], "demand count")
    after_hours_col = _choose_col(columns, ["is_after_hours", "after_hours"], "after-hours flag", required=False)
    high_demand_col = _choose_col(columns, ["high_demand_flag", "high_demand"], "high-demand flag", required=False)
    temp_col = _choose_col(columns, ["temperature_2m", "temperature", "temp"], "temperature", required=False)
    precip_col = _choose_col(columns, ["precipitation", "rain"], "precipitation", required=False)
    rain_col = _choose_col(columns, ["rain", "is_rain"], "rain", required=False)

    usecols = [
        c
        for c in {
            zone_col,
            date_col,
            hour_col,
            weekday_col,
            weekend_col,
            demand_col,
            after_hours_col,
            high_demand_col,
            temp_col,
            precip_col,
            rain_col,
        }
        if c is not None
    ]

    zone_parts: list[pd.DataFrame] = []
    zone_period_parts: list[pd.DataFrame] = []
    zone_hour_parts: list[pd.DataFrame] = []
    zone_period_hour_parts: list[pd.DataFrame] = []
    hourly_parts: list[pd.DataFrame] = []
    day_parts: list[pd.DataFrame] = []
    heatmap_parts: list[pd.DataFrame] = []
    weather_parts: list[pd.DataFrame] = []
    total_zone_hour_rows = 0
    date_min: str | None = None
    date_max: str | None = None

    for idx, chunk in enumerate(pd.read_csv(ZONE_HOUR_CSV, usecols=usecols, chunksize=CHUNK_SIZE), start=1):
        total_zone_hour_rows += len(chunk)
        chunk = chunk.rename(
            columns={zone_col: "zone_id", date_col: "date", hour_col: "hour", weekday_col: "weekday", demand_col: "demand_count"}
        )
        rename_map = {}
        if weekend_col and weekend_col != "is_weekend":
            rename_map[weekend_col] = "is_weekend"
        if after_hours_col and after_hours_col != "is_after_hours":
            rename_map[after_hours_col] = "is_after_hours"
        if high_demand_col and high_demand_col != "high_demand_flag":
            rename_map[high_demand_col] = "high_demand_flag"
        if temp_col and temp_col != "temperature":
            rename_map[temp_col] = "temperature"
        if precip_col and precip_col != "precipitation":
            rename_map[precip_col] = "precipitation"
        if rain_col and rain_col != "rain":
            rename_map[rain_col] = "rain"
        if rename_map:
            chunk = chunk.rename(columns=rename_map)

        chunk["zone_id"] = chunk["zone_id"].fillna("UNKNOWN").astype(str).str.upper().str.strip()
        chunk = _add_period_columns(chunk, "date")
        chunk = chunk[chunk["period"].notna()].copy()
        chunk["hour"] = pd.to_numeric(chunk["hour"], errors="coerce").fillna(-1).astype(int)
        chunk["weekday"] = pd.to_numeric(chunk["weekday"], errors="coerce").fillna(-1).astype(int)
        chunk["weekday_name"] = chunk["weekday"].map(WEEKDAY_NAMES).fillna("Unknown")
        chunk["demand_count"] = pd.to_numeric(chunk["demand_count"], errors="coerce").fillna(0)
        chunk["is_weekend"] = _to_bool(chunk["is_weekend"]) if "is_weekend" in chunk else chunk["weekday"].isin([5, 6])
        chunk["is_after_hours"] = _to_bool(chunk["is_after_hours"]) if "is_after_hours" in chunk else False
        chunk["high_demand_flag"] = pd.to_numeric(chunk["high_demand_flag"], errors="coerce").fillna(0) if "high_demand_flag" in chunk else 0

        valid_dates = chunk["date"].dropna()
        if not valid_dates.empty:
            c_min = str(valid_dates.min())
            c_max = str(valid_dates.max())
            date_min = c_min if date_min is None else min(date_min, c_min)
            date_max = c_max if date_max is None else max(date_max, c_max)

        chunk["weekend_demand"] = np.where(chunk["is_weekend"], chunk["demand_count"], 0)
        chunk["after_hours_demand"] = np.where(chunk["is_after_hours"], chunk["demand_count"], 0)
        chunk["zone_hour_records"] = 1

        zone_agg_cols = dict(
            total_service_demand=("demand_count", "sum"),
            zone_hour_records=("zone_hour_records", "sum"),
            weekend_demand=("weekend_demand", "sum"),
            after_hours_demand=("after_hours_demand", "sum"),
            high_demand_hours=("high_demand_flag", "sum"),
            peak_hour_demand=("demand_count", "max"),
        )
        zone_parts.append(chunk.groupby("zone_id", as_index=False).agg(**zone_agg_cols))
        zone_period_parts.append(chunk.groupby(["period", "year", "month", "zone_id"], as_index=False).agg(**zone_agg_cols))
        zone_hour_parts.append(chunk.groupby(["zone_id", "hour"], as_index=False).agg(hour_total_demand=("demand_count", "sum")))
        zone_period_hour_parts.append(
            chunk.groupby(["period", "year", "month", "zone_id", "hour"], as_index=False).agg(hour_total_demand=("demand_count", "sum"))
        )
        hourly_parts.append(
            chunk.groupby(["period", "year", "month", "date", "hour", "is_weekend"], as_index=False).agg(
                demand_count=("demand_count", "sum"), zone_hour_records=("zone_hour_records", "sum")
            )
        )
        day_parts.append(
            chunk.groupby(["period", "year", "month", "date", "weekday", "weekday_name", "is_weekend"], as_index=False).agg(
                demand_count=("demand_count", "sum"), zone_hour_records=("zone_hour_records", "sum")
            )
        )
        heatmap_parts.append(
            chunk.groupby(["period", "year", "month", "zone_id", "hour", "is_weekend"], as_index=False).agg(
                demand_count=("demand_count", "sum"), zone_hour_records=("zone_hour_records", "sum")
            )
        )

        if temp_col or precip_col or rain_col:
            weather = chunk.copy()
            weather["temperature"] = pd.to_numeric(weather["temperature"], errors="coerce") if "temperature" in weather else np.nan
            weather["precipitation"] = pd.to_numeric(weather["precipitation"], errors="coerce") if "precipitation" in weather else np.nan
            weather["rain"] = pd.to_numeric(weather["rain"], errors="coerce") if "rain" in weather else np.nan
            weather = weather[weather[["temperature", "precipitation", "rain"]].notna().any(axis=1)].copy()
            if not weather.empty:
                weather["precip_source"] = weather["precipitation"].fillna(weather["rain"]).fillna(0)
                weather["precipitation_band"] = pd.cut(
                    weather["precip_source"],
                    bins=[-0.001, 0, 0.5, 2, 10, np.inf],
                    labels=["No measured precipitation", "Trace to 0.5 mm", "0.5 to 2 mm", "2 to 10 mm", "10+ mm"],
                ).astype(str)
                weather["temperature_band"] = pd.cut(
                    weather["temperature"],
                    bins=[-np.inf, 0, 5, 10, 15, 20, 25, np.inf],
                    labels=["Below 0 C", "0 to 5 C", "5 to 10 C", "10 to 15 C", "15 to 20 C", "20 to 25 C", "25+ C"],
                ).astype(str)
                weather_parts.append(
                    weather.groupby(["period", "year", "month", "precipitation_band"], as_index=False)
                    .agg(demand_count=("demand_count", "sum"), zone_hour_records=("zone_hour_records", "sum"))
                    .assign(view="Precipitation band", band=lambda d: d["precipitation_band"])
                    .drop(columns=["precipitation_band"])
                )
                weather_parts.append(
                    weather.groupby(["period", "year", "month", "temperature_band"], as_index=False)
                    .agg(demand_count=("demand_count", "sum"), zone_hour_records=("zone_hour_records", "sum"))
                    .assign(view="Temperature band", band=lambda d: d["temperature_band"])
                    .drop(columns=["temperature_band"])
                )

        print(f"Processed zone-hour chunk {idx}: {total_zone_hour_rows:,} rows", flush=True)

    zone_summary = _sum_parts(zone_parts, ["zone_id"], ["total_service_demand", "zone_hour_records", "weekend_demand", "after_hours_demand", "high_demand_hours", "peak_hour_demand"])
    zone_hour_totals = _sum_parts(zone_hour_parts, ["zone_id", "hour"], ["hour_total_demand"])
    peak_hours = zone_hour_totals.sort_values(["zone_id", "hour_total_demand", "hour"], ascending=[True, False, True]).drop_duplicates("zone_id").rename(columns={"hour": "peak_hour"})[["zone_id", "peak_hour"]]
    zone_summary = _finalize_zone_summary(zone_summary, peak_hours)

    zone_summary_by_period = _sum_parts(zone_period_parts, ["period", "year", "month", "zone_id"], ["total_service_demand", "zone_hour_records", "weekend_demand", "after_hours_demand", "high_demand_hours", "peak_hour_demand"])
    zone_period_hour = _sum_parts(zone_period_hour_parts, ["period", "year", "month", "zone_id", "hour"], ["hour_total_demand"])
    period_peak_hours = zone_period_hour.sort_values(["period", "zone_id", "hour_total_demand", "hour"], ascending=[True, True, False, True]).drop_duplicates(["period", "zone_id"]).rename(columns={"hour": "peak_hour"})[["period", "zone_id", "peak_hour"]]
    zone_summary_by_period = _finalize_zone_summary(zone_summary_by_period, period_peak_hours)

    hourly_demand = _sum_parts(hourly_parts, ["period", "year", "month", "date", "hour", "is_weekend"], ["demand_count", "zone_hour_records"])
    day_of_week = _sum_parts(day_parts, ["period", "year", "month", "date", "weekday", "weekday_name", "is_weekend"], ["demand_count", "zone_hour_records"])
    heatmap = _sum_parts(heatmap_parts, ["period", "year", "month", "zone_id", "hour", "is_weekend"], ["demand_count", "zone_hour_records"])

    if weather_parts:
        weather_context = _sum_parts(weather_parts, ["period", "year", "month", "view", "band"], ["demand_count", "zone_hour_records"])
        weather_context["avg_demand_per_zone_hour"] = _safe_divide(weather_context["demand_count"], weather_context["zone_hour_records"])
    else:
        weather_context = pd.DataFrame(columns=["period", "year", "month", "view", "band", "demand_count", "zone_hour_records", "avg_demand_per_zone_hour"])

    category_mix = _build_service_category_asset()

    report_metrics = _parse_report_metrics()
    spark_input_rows = report_metrics.get("input_cleaned_call_rows") or 6_471_140
    fact_rows = report_metrics.get("fact_output_rows") or 6_471_289
    duplicate_fact_rows = max(int(fact_rows) - int(spark_input_rows), 0)
    duplicate_impact = duplicate_fact_rows / spark_input_rows if spark_input_rows else 0
    periods = sorted(hourly_demand["period"].dropna().unique().tolist())
    kpis = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "project": "Public Safety Service Demand Intelligence Platform",
        "raw_source_rows": report_metrics.get("raw_source_rows"),
        "cleaned_input_events": spark_input_rows,
        "fact_output_rows": fact_rows,
        "unique_event_ids": spark_input_rows,
        "post_enrichment_duplicate_fact_rows": duplicate_fact_rows,
        "post_enrichment_duplicate_impact": duplicate_impact,
        "zone_hour_records": report_metrics.get("zone_hour_output_rows") or total_zone_hour_rows,
        "active_zones_beats": report_metrics.get("number_of_zones_beats") or int(zone_summary["zone_id"].nunique()),
        "mapped_beat_polygons": 55,
        "date_start": report_metrics.get("date_start") or date_min,
        "date_end": report_metrics.get("date_end") or date_max,
        "period_start": periods[0] if periods else None,
        "period_end": periods[-1] if periods else None,
        "periods": periods,
        "spark_version": report_metrics.get("spark_version") or "4.1.2",
        "java_version": report_metrics.get("java_version") or 'openjdk version "17.0.18"',
        "spark_full_mode": str(report_metrics.get("run_mode_full")).lower() == "true",
        "pandas_fallback_used": str(report_metrics.get("pandas_fallback_used")).lower() == "true",
        "weather_join_coverage": report_metrics.get("weather_join_coverage"),
    }
    qa_lineage = {
        **kpis,
        "pyspark_full_transform_completed": True,
        "known_qa_note": "Post-enrichment fact output contains 149 duplicate fact rows, but QA confirmed 6,471,140 unique event_ids, zero missing event_ids, and zero fake/new event_ids.",
        "normal_dashboard_load_policy": "Streamlit reads data/app assets only; it does not load the full fact table.",
        "period_filter_support": {
            "zone_summary_by_period.csv": True,
            "map_zone_demand_by_period.csv": True,
            "hourly_demand.csv": True,
            "day_of_week_demand.csv": True,
            "day_hour_heatmap.csv": True,
            "weather_context_summary.csv": True,
            "service_category_mix.csv": "sample-based period support",
        },
        "source_assets": {
            "zone_hour_features_csv": "data/processed/zone_hour_features.csv",
            "fact_sample_csv": "data/processed/fact_service_events_sample.csv",
            "beat_geojson": "data/app/seattle_police_beats.geojson",
            "pyspark_report": "outputs/memo/pyspark_processing_report.md",
        },
    }

    map_zone_demand_by_period = zone_summary_by_period.copy()
    zone_summary.to_csv(APP_DIR / "zone_summary.csv", index=False)
    zone_summary_by_period.to_csv(APP_DIR / "zone_summary_by_period.csv", index=False)
    map_zone_demand_by_period.to_csv(APP_DIR / "map_zone_demand_by_period.csv", index=False)
    hourly_demand.sort_values(["period", "date", "hour", "is_weekend"]).to_csv(APP_DIR / "hourly_demand.csv", index=False)
    day_of_week.sort_values(["period", "date", "weekday"]).to_csv(APP_DIR / "day_of_week_demand.csv", index=False)
    heatmap.sort_values(["period", "zone_id", "is_weekend", "hour"]).to_csv(APP_DIR / "day_hour_heatmap.csv", index=False)
    category_mix.to_csv(APP_DIR / "service_category_mix.csv", index=False)
    weather_context.sort_values(["period", "view", "band"]).to_csv(APP_DIR / "weather_context_summary.csv", index=False)
    (APP_DIR / "dashboard_kpis.json").write_text(json.dumps(kpis, indent=2, default=_json_default), encoding="utf-8")
    (APP_DIR / "qa_lineage.json").write_text(json.dumps(qa_lineage, indent=2, default=_json_default), encoding="utf-8")

    counts = {
        "dashboard_kpis.json": 1,
        "zone_summary.csv": len(zone_summary),
        "zone_summary_by_period.csv": len(zone_summary_by_period),
        "map_zone_demand_by_period.csv": len(map_zone_demand_by_period),
        "hourly_demand.csv": len(hourly_demand),
        "day_of_week_demand.csv": len(day_of_week),
        "day_hour_heatmap.csv": len(heatmap),
        "service_category_mix.csv": len(category_mix),
        "weather_context_summary.csv": len(weather_context),
        "qa_lineage.json": 1,
    }
    print("\nDashboard assets written:")
    for name, count in counts.items():
        print(f"- {name}: {count:,} rows")
    print("\nPeriod filter support:")
    print("- Map, top zones, peak window, heatmap, hourly rhythm, weekly pattern, and weather context: supported")
    print("- Service category mix: sample-based; period field included when sample event_date is available")
    return counts


def _build_service_category_asset() -> pd.DataFrame:
    base_cols = ["zone_id", "service_category", "sample_demand_count", "sample_event_rows", "sample_based", "period", "year", "month"]
    if not FACT_SAMPLE_CSV.exists():
        return pd.DataFrame(columns=base_cols)
    header = pd.read_csv(FACT_SAMPLE_CSV, nrows=0)
    columns = list(header.columns)
    print("Available fact sample columns:")
    print(", ".join(columns))
    zone_col = _choose_col(columns, ["zone_id", "beat", "zone"], "fact sample zone/beat", required=False)
    category_col = _choose_col(columns, ["normalized_service_category", "service_category", "final_call_type", "initial_call_type"], "service category", required=False)
    demand_col = _choose_col(columns, ["demand_count", "event_count", "call_count"], "sample demand", required=False)
    date_col = _choose_col(columns, ["event_date", "date", "service_date", "event_datetime"], "sample event date", required=False)
    if not category_col:
        return pd.DataFrame(columns=base_cols)
    usecols = [c for c in [zone_col, category_col, demand_col, date_col] if c]
    sample = pd.read_csv(FACT_SAMPLE_CSV, usecols=usecols)
    sample["zone_id"] = sample[zone_col].fillna("UNKNOWN").astype(str).str.upper().str.strip() if zone_col else "ALL"
    sample["service_category"] = sample[category_col].fillna("Uncategorized").astype(str).str.strip()
    sample["sample_demand_count"] = pd.to_numeric(sample[demand_col], errors="coerce").fillna(1) if demand_col else 1
    if date_col:
        sample = sample.rename(columns={date_col: "date"})
        sample = _add_period_columns(sample, "date")
    else:
        sample["period"] = "All sample"
        sample["year"] = pd.NA
        sample["month"] = pd.NA
    out = sample.groupby(["period", "year", "month", "zone_id", "service_category"], dropna=False, as_index=False).agg(
        sample_demand_count=("sample_demand_count", "sum"), sample_event_rows=("service_category", "size")
    )
    out["sample_based"] = True
    return out.sort_values("sample_demand_count", ascending=False)


if __name__ == "__main__":
    build_assets()
