from __future__ import annotations

import numpy as np
import pandas as pd
import sqlite3

from src import config
from src.utils.data_quality import build_quality_outputs
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


def _scale(series: pd.Series) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce").fillna(0)
    min_v, max_v = s.min(), s.max()
    if max_v == min_v:
        return pd.Series(50, index=s.index)
    return ((s - min_v) / (max_v - min_v) * 100).round(1)


def _zone_summary(fact: pd.DataFrame, zone_hour: pd.DataFrame) -> pd.DataFrame:
    zone = fact.groupby("zone_id").agg(
        total_events=("demand_count", "sum"),
        first_event=("event_datetime", "min"),
        last_event=("event_datetime", "max"),
        primary_precinct=("precinct", lambda s: s.dropna().mode().iloc[0] if not s.dropna().empty else pd.NA),
        primary_sector=("sector", lambda s: s.dropna().mode().iloc[0] if not s.dropna().empty else pd.NA),
        top_category=("normalized_service_category", lambda s: s.dropna().mode().iloc[0] if not s.dropna().empty else pd.NA),
    ).reset_index()
    zh = zone_hour.groupby("zone_id").agg(
        avg_hourly_demand=("target_demand_count", "mean"),
        demand_volatility=("target_demand_count", "std"),
        after_hours_share=("is_after_hours", "mean"),
        weekend_share=("is_weekend", "mean"),
        high_demand_rate=("high_demand_flag", "mean"),
    ).reset_index()
    out = zone.merge(zh, on="zone_id", how="left")
    out["workload_risk_score"] = (
        _scale(out["total_events"]) * 0.35
        + _scale(out["avg_hourly_demand"]) * 0.25
        + _scale(out["demand_volatility"]) * 0.20
        + _scale(out["after_hours_share"]) * 0.10
        + _scale(out["weekend_share"]) * 0.10
    ).round(1)
    return out.sort_values("workload_risk_score", ascending=False)


def _recommendations(zone_summary: pd.DataFrame, category_summary: pd.DataFrame) -> pd.DataFrame:
    top_zone = zone_summary.iloc[0]["zone_id"] if not zone_summary.empty else "highest-risk zones"
    top_category = category_summary.iloc[0]["normalized_service_category"] if not category_summary.empty else "top service categories"
    rows = [
        ("REC-001", "Demand-spike alerting", "Command center leaders", f"High workload-risk concentration in {top_zone}", "Create configurable zone-hour alerts for emerging demand spikes.", "High"),
        ("REC-002", "Zone-level workload-risk scoring", "Client service and operations teams", "Risk score blends demand volume, volatility, weekend, and after-hours patterns.", "Use a recurring workload-risk view during client service reviews.", "High"),
        ("REC-003", "Command-center demand heatmap", "Supervisors and service managers", "Demand differs materially by hour, weekday, and zone.", "Build heatmap widgets for time-of-week and zone demand visibility.", "High"),
        ("REC-004", "Category mix trend monitoring", "Product managers", f"{top_category} is a major workload driver in this run.", "Track category mix changes to prioritize workflow and reporting enhancements.", "Medium"),
        ("REC-005", "Staffing/resource scenario planner", "Business operations analysts", "High-demand zone-hours can be forecasted from historical patterns.", "Use Excel/Hex planning tools for coverage gap and allocation scenarios.", "High"),
        ("REC-006", "Weather-aware demand monitoring", "Client service teams", "Weather features are joined at hourly granularity.", "Surface precipitation and temperature context in service-demand reviews.", "Medium"),
        ("REC-007", "Recurring demand pattern packet", "Account and product teams", "Monthly, weekend, and after-hours patterns can be refreshed locally.", "Generate a recurring service-demand trend packet for stakeholder updates.", "Medium"),
        ("REC-008", "Territory workload review workflow", "Operations planning teams", "Cluster profiles segment zones into interpretable demand profiles.", "Use clusters to guide territory/zone workload review conversations.", "Medium"),
    ]
    return pd.DataFrame(rows, columns=["recommendation_id", "recommendation_theme", "target_user", "evidence_signal", "product_service_opportunity", "priority"])


def _write_memos(fact_count: int, zone_count: int, zone_summary: pd.DataFrame, category: pd.DataFrame, recommendations: pd.DataFrame) -> None:
    executive = [
        "# Executive Summary",
        "",
        "This project analyzes public safety service-demand metadata to show where and when operational workload concentrates, which service categories drive demand, and how zone-level workload risk can support command-center visibility and client service planning.",
        "",
        f"- Service events processed: `{fact_count:,}`",
        f"- Distinct zones/beats: `{zone_count:,}`",
        f"- Highest workload-risk zone: `{zone_summary.iloc[0]['zone_id'] if not zone_summary.empty else 'n/a'}`",
        f"- Top service category: `{category.iloc[0]['normalized_service_category'] if not category.empty else 'n/a'}`",
        "",
        "The outputs are designed for Hex, Tableau, Excel, and Streamlit so product, service, and business stakeholders can inspect demand trends without rerunning the full pipeline.",
    ]
    (config.MEMO_OUTPUT_DIR / "executive_summary.md").write_text("\n".join(executive), encoding="utf-8")
    rec_lines = ["# Product/Service Recommendations", ""]
    for rec in recommendations.to_dict(orient="records"):
        rec_lines.append(f"## {rec['recommendation_theme']}")
        rec_lines.append("")
        rec_lines.append(f"- Priority: `{rec['priority']}`")
        rec_lines.append(f"- Target user: {rec['target_user']}")
        rec_lines.append(f"- Evidence signal: {rec['evidence_signal']}")
        rec_lines.append(f"- Product/service opportunity: {rec['product_service_opportunity']}")
        rec_lines.append("")
    (config.MEMO_OUTPUT_DIR / "product_service_recommendations.md").write_text("\n".join(rec_lines), encoding="utf-8")
    (config.MEMO_OUTPUT_DIR / "limitations.md").write_text(
        "# Limitations\n\nPublic operational metadata can be incomplete, delayed, duplicated, or inconsistently categorized. Weather joins assume local hourly timestamps. Geography joins use available beat identifiers and should be validated against agency-specific boundary definitions. Forecasts are planning aids for aggregate workload visibility and should not be used for individual-level decisions.\n",
        encoding="utf-8",
    )


def _quality_from_sql(conn: sqlite3.Connection, fact_count: int, zone_hour_count: int) -> pd.DataFrame:
    rows = [
        {"metric": "sample_mode", "value": str(config.SAMPLE_MODE), "detail": "Pipeline run mode"},
        {"metric": "fact_rows", "value": fact_count, "detail": "Rows in fact_service_events"},
        {"metric": "zone_hour_rows", "value": zone_hour_count, "detail": "Rows in zone_hour_features"},
    ]
    q = pd.read_sql_query(
        """
        SELECT
          COUNT(DISTINCT zone_id) AS distinct_zones,
          COUNT(DISTINCT normalized_service_category) AS distinct_categories,
          SUM(CASE WHEN temperature_2m IS NOT NULL THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS weather_join_coverage,
          SUM(CASE WHEN latitude IS NULL THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS missing_latitude_pct,
          SUM(CASE WHEN longitude IS NULL THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS missing_longitude_pct
        FROM fact_service_events
        """,
        conn,
    ).iloc[0]
    rows.extend(
        [
            {"metric": "distinct_zone_id", "value": int(q["distinct_zones"]), "detail": "Zone/beat coverage"},
            {"metric": "distinct_normalized_service_category", "value": int(q["distinct_categories"]), "detail": "Service category coverage"},
            {"metric": "weather_join_coverage_pct", "value": round(float(q["weather_join_coverage"]) * 100, 2), "detail": "Hourly weather join coverage"},
            {"metric": "missing_latitude_pct", "value": round(float(q["missing_latitude_pct"]) * 100, 2), "detail": "Latitude missingness"},
            {"metric": "missing_longitude_pct", "value": round(float(q["missing_longitude_pct"]) * 100, 2), "detail": "Longitude missingness"},
        ]
    )
    quality = pd.DataFrame(rows)
    quality.to_csv(config.HEX_OUTPUT_DIR / "hex_data_quality_summary.csv", index=False)
    (config.MEMO_OUTPUT_DIR / "data_quality_notes.md").write_text(
        "\n".join(
            [
                "# Data Quality Notes",
                "",
                f"- Run mode full: `{not config.SAMPLE_MODE}`",
                f"- Fact rows: `{fact_count:,}`",
                f"- Zone-hour rows: `{zone_hour_count:,}`",
                f"- Weather join coverage: `{float(q['weather_join_coverage']):.2%}`",
                "",
                "Quality metrics were generated from SQLite aggregate queries to avoid loading the full fact table into memory.",
            ]
        ),
        encoding="utf-8",
    )
    return quality


def _build_hex_outputs_sqlite() -> None:
    conn = sqlite3.connect(config.SQLITE_DB_PATH)
    try:
        fact_count = conn.execute("SELECT COUNT(*) FROM fact_service_events").fetchone()[0]
        zone_hour_count = conn.execute("SELECT COUNT(*) FROM zone_hour_features").fetchone()[0]
        hourly = pd.read_sql_query(
            """
            SELECT weekday, weekday_name, event_hour, COUNT(*) AS demand_count
            FROM fact_service_events
            GROUP BY weekday, weekday_name, event_hour
            ORDER BY weekday, event_hour
            """,
            conn,
        )
        hourly.to_csv(config.HEX_OUTPUT_DIR / "hex_hourly_demand.csv", index=False)

        category = pd.read_sql_query(
            """
            SELECT normalized_service_category, COUNT(*) AS demand_count
            FROM fact_service_events
            GROUP BY normalized_service_category
            ORDER BY demand_count DESC
            """,
            conn,
        )
        category["share_of_total"] = category["demand_count"] / max(category["demand_count"].sum(), 1)
        category.to_csv(config.HEX_OUTPUT_DIR / "hex_category_summary.csv", index=False)

        zone_base = pd.read_sql_query(
            """
            WITH category_rank AS (
              SELECT zone_id, normalized_service_category, COUNT(*) AS category_count,
                     ROW_NUMBER() OVER (PARTITION BY zone_id ORDER BY COUNT(*) DESC) AS rn
              FROM fact_service_events
              GROUP BY zone_id, normalized_service_category
            )
            SELECT
              f.zone_id,
              COUNT(*) AS total_events,
              MIN(f.event_datetime) AS first_event,
              MAX(f.event_datetime) AS last_event,
              MAX(f.precinct) AS primary_precinct,
              MAX(f.sector) AS primary_sector,
              MAX(CASE WHEN cr.rn = 1 THEN cr.normalized_service_category END) AS top_category
            FROM fact_service_events f
            LEFT JOIN category_rank cr ON f.zone_id = cr.zone_id AND cr.rn = 1
            GROUP BY f.zone_id
            """,
            conn,
        )
        zh = pd.read_sql_query(
            """
            SELECT zone_id,
                   AVG(target_demand_count) AS avg_hourly_demand,
                   AVG((target_demand_count - 0.0) * (target_demand_count - 0.0)) - AVG(target_demand_count) * AVG(target_demand_count) AS demand_volatility,
                   AVG(CAST(is_after_hours AS REAL)) AS after_hours_share,
                   AVG(CAST(is_weekend AS REAL)) AS weekend_share,
                   AVG(CAST(high_demand_flag AS REAL)) AS high_demand_rate
            FROM zone_hour_features
            GROUP BY zone_id
            """,
            conn,
        )
        zone_summary = zone_base.merge(zh, on="zone_id", how="left")
        zone_summary["workload_risk_score"] = (
            _scale(zone_summary["total_events"]) * 0.35
            + _scale(zone_summary["avg_hourly_demand"]) * 0.25
            + _scale(zone_summary["demand_volatility"]) * 0.20
            + _scale(zone_summary["after_hours_share"]) * 0.10
            + _scale(zone_summary["weekend_share"]) * 0.10
        ).round(1)
        zone_summary = zone_summary.sort_values("workload_risk_score", ascending=False)
        zone_summary.to_csv(config.HEX_OUTPUT_DIR / "hex_zone_summary.csv", index=False)
        zone_summary[["zone_id", "workload_risk_score", "total_events", "avg_hourly_demand", "after_hours_share", "weekend_share", "high_demand_rate"]].to_csv(
            config.HEX_OUTPUT_DIR / "hex_workload_risk_scores.csv", index=False
        )

        weather_summary = pd.read_sql_query(
            """
            SELECT
              CASE WHEN COALESCE(precipitation,0) + COALESCE(rain,0) > 0 THEN 'precipitation_observed' ELSE 'no_precipitation' END AS precipitation_flag,
              ROUND(temperature_2m, 0) AS temperature_bucket,
              COUNT(*) AS observed_zone_hours,
              AVG(target_demand_count) AS avg_demand,
              AVG(CAST(high_demand_flag AS REAL)) AS high_demand_rate
            FROM zone_hour_features
            GROUP BY precipitation_flag, temperature_bucket
            ORDER BY temperature_bucket
            """,
            conn,
        )
        weather_summary.to_csv(config.HEX_OUTPUT_DIR / "hex_weather_demand_summary.csv", index=False)

        recommendations = _recommendations(zone_summary, category)
        recommendations.to_csv(config.HEX_OUTPUT_DIR / "hex_recommendations.csv", index=False)

        kpi_query = pd.read_sql_query(
            """
            SELECT
              MIN(event_datetime) AS date_start,
              MAX(event_datetime) AS date_end,
              COUNT(DISTINCT zone_id) AS unique_zones,
              COUNT(DISTINCT normalized_service_category) AS unique_categories
            FROM fact_service_events
            """,
            conn,
        ).iloc[0]
        kpis = pd.DataFrame(
            [
                {"metric": "total_service_events", "value": fact_count, "detail": "Rows in the fact table"},
                {"metric": "date_start", "value": kpi_query["date_start"], "detail": "Earliest service-event timestamp"},
                {"metric": "date_end", "value": kpi_query["date_end"], "detail": "Latest service-event timestamp"},
                {"metric": "unique_zones", "value": int(kpi_query["unique_zones"]), "detail": "Distinct zones/beats"},
                {"metric": "unique_categories", "value": int(kpi_query["unique_categories"]), "detail": "Distinct normalized service categories"},
                {"metric": "top_workload_risk_zone", "value": zone_summary.iloc[0]["zone_id"] if not zone_summary.empty else "n/a", "detail": "Highest workload-risk score"},
                {"metric": "top_service_category", "value": category.iloc[0]["normalized_service_category"] if not category.empty else "n/a", "detail": "Largest event category"},
                {"metric": "sample_mode", "value": str(config.SAMPLE_MODE), "detail": "Whether the run used sample mode"},
            ]
        )
        kpis.to_csv(config.HEX_OUTPUT_DIR / "hex_executive_kpis.csv", index=False)
        _quality_from_sql(conn, fact_count, zone_hour_count)
        _write_memos(fact_count, int(kpi_query["unique_zones"]), zone_summary, category, recommendations)
    finally:
        conn.close()


def build_hex_outputs() -> None:
    config.ensure_directories()
    if not config.SAMPLE_MODE and config.SQLITE_DB_PATH.exists():
        _build_hex_outputs_sqlite()
        if not (config.HEX_OUTPUT_DIR / "hex_cluster_profiles.csv").exists():
            pd.DataFrame().to_csv(config.HEX_OUTPUT_DIR / "hex_cluster_profiles.csv", index=False)
        if not (config.HEX_OUTPUT_DIR / "hex_model_predictions.csv").exists():
            pd.DataFrame().to_csv(config.HEX_OUTPUT_DIR / "hex_model_predictions.csv", index=False)
        logger.info("Hex-ready outputs written from SQLite full-mode aggregates")
        return

    fact = pd.read_parquet(config.FACT_EVENTS_PARQUET)
    fact["event_datetime"] = pd.to_datetime(fact["event_datetime"], errors="coerce")
    zone_hour = pd.read_csv(config.ZONE_HOUR_FEATURES_CSV, parse_dates=["date", "date_hour"])

    hourly = fact.groupby(["weekday", "weekday_name", "event_hour"], dropna=False).size().reset_index(name="demand_count")
    hourly.to_csv(config.HEX_OUTPUT_DIR / "hex_hourly_demand.csv", index=False)

    category = fact.groupby("normalized_service_category", dropna=False).size().reset_index(name="demand_count").sort_values("demand_count", ascending=False)
    category["share_of_total"] = category["demand_count"] / max(category["demand_count"].sum(), 1)
    category.to_csv(config.HEX_OUTPUT_DIR / "hex_category_summary.csv", index=False)

    zone_summary = _zone_summary(fact, zone_hour)
    zone_summary.to_csv(config.HEX_OUTPUT_DIR / "hex_zone_summary.csv", index=False)
    zone_summary[["zone_id", "workload_risk_score", "total_events", "avg_hourly_demand", "after_hours_share", "weekend_share", "high_demand_rate"]].to_csv(config.HEX_OUTPUT_DIR / "hex_workload_risk_scores.csv", index=False)

    weather_summary = zone_hour.assign(
        precipitation_flag=np.where(zone_hour[["precipitation", "rain"]].fillna(0).sum(axis=1) > 0, "precipitation_observed", "no_precipitation"),
        temperature_bucket=pd.to_numeric(zone_hour["temperature_2m"], errors="coerce").round(0),
    ).groupby(["precipitation_flag", "temperature_bucket"], dropna=False).agg(
        observed_zone_hours=("target_demand_count", "size"),
        avg_demand=("target_demand_count", "mean"),
        high_demand_rate=("high_demand_flag", "mean"),
    ).reset_index()
    weather_summary.to_csv(config.HEX_OUTPUT_DIR / "hex_weather_demand_summary.csv", index=False)

    recommendations = _recommendations(zone_summary, category)
    recommendations.to_csv(config.HEX_OUTPUT_DIR / "hex_recommendations.csv", index=False)

    kpis = pd.DataFrame(
        [
            {"metric": "total_service_events", "value": len(fact), "detail": "Rows in the fact table"},
            {"metric": "date_start", "value": str(fact["event_datetime"].min()), "detail": "Earliest service-event timestamp"},
            {"metric": "date_end", "value": str(fact["event_datetime"].max()), "detail": "Latest service-event timestamp"},
            {"metric": "unique_zones", "value": fact["zone_id"].nunique(), "detail": "Distinct zones/beats"},
            {"metric": "unique_categories", "value": fact["normalized_service_category"].nunique(), "detail": "Distinct normalized service categories"},
            {"metric": "top_workload_risk_zone", "value": zone_summary.iloc[0]["zone_id"] if not zone_summary.empty else "n/a", "detail": "Highest workload-risk score"},
            {"metric": "top_service_category", "value": category.iloc[0]["normalized_service_category"] if not category.empty else "n/a", "detail": "Largest event category"},
            {"metric": "sample_mode", "value": str(config.SAMPLE_MODE), "detail": "Whether the run used sample mode"},
        ]
    )
    kpis.to_csv(config.HEX_OUTPUT_DIR / "hex_executive_kpis.csv", index=False)

    build_quality_outputs(fact, zone_hour, config.SAMPLE_MODE)
    if not (config.HEX_OUTPUT_DIR / "hex_cluster_profiles.csv").exists():
        pd.DataFrame().to_csv(config.HEX_OUTPUT_DIR / "hex_cluster_profiles.csv", index=False)
    if not (config.HEX_OUTPUT_DIR / "hex_model_predictions.csv").exists():
        pd.DataFrame().to_csv(config.HEX_OUTPUT_DIR / "hex_model_predictions.csv", index=False)

    executive = [
        "# Executive Summary",
        "",
        "This project analyzes public safety service-demand metadata to show where and when operational workload concentrates, which service categories drive demand, and how zone-level workload risk can support command-center visibility and client service planning.",
        "",
        f"- Service events processed: `{len(fact):,}`",
        f"- Distinct zones/beats: `{fact['zone_id'].nunique():,}`",
        f"- Highest workload-risk zone: `{zone_summary.iloc[0]['zone_id'] if not zone_summary.empty else 'n/a'}`",
        f"- Top service category: `{category.iloc[0]['normalized_service_category'] if not category.empty else 'n/a'}`",
        "",
        "The outputs are designed for Hex, Tableau, Excel, and Streamlit so product, service, and business stakeholders can inspect demand trends without rerunning the full pipeline.",
    ]
    (config.MEMO_OUTPUT_DIR / "executive_summary.md").write_text("\n".join(executive), encoding="utf-8")
    rec_lines = ["# Product/Service Recommendations", ""]
    for rec in recommendations.to_dict(orient="records"):
        rec_lines.append(f"## {rec['recommendation_theme']}")
        rec_lines.append("")
        rec_lines.append(f"- Priority: `{rec['priority']}`")
        rec_lines.append(f"- Target user: {rec['target_user']}")
        rec_lines.append(f"- Evidence signal: {rec['evidence_signal']}")
        rec_lines.append(f"- Product/service opportunity: {rec['product_service_opportunity']}")
        rec_lines.append("")
    (config.MEMO_OUTPUT_DIR / "product_service_recommendations.md").write_text("\n".join(rec_lines), encoding="utf-8")
    (config.MEMO_OUTPUT_DIR / "limitations.md").write_text(
        "# Limitations\n\nPublic operational metadata can be incomplete, delayed, duplicated, or inconsistently categorized. Weather joins assume local hourly timestamps. Geography joins use available beat identifiers and should be validated against agency-specific boundary definitions. Forecasts are planning aids for aggregate workload visibility, not individual-level or enforcement-oriented decision tools.\n",
        encoding="utf-8",
    )
    logger.info("Hex-ready outputs written")


if __name__ == "__main__":
    build_hex_outputs()
