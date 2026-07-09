from __future__ import annotations

from pathlib import Path

import pandas as pd

from src import config


def _pct(value: float) -> float:
    return round(float(value) * 100, 2)


def build_quality_outputs(
    fact: pd.DataFrame,
    zone_hour: pd.DataFrame | None = None,
    sample_mode: bool | None = None,
    output_csv: Path | None = None,
    output_md: Path | None = None,
) -> pd.DataFrame:
    config.ensure_directories()
    if sample_mode is None:
        sample_mode = config.SAMPLE_MODE
    if output_csv is None:
        output_csv = config.HEX_OUTPUT_DIR / "hex_data_quality_summary.csv"
    if output_md is None:
        output_md = config.MEMO_OUTPUT_DIR / "data_quality_notes.md"

    rows: list[dict] = []
    rows.append({"metric": "sample_mode", "value": str(sample_mode), "detail": "Pipeline run mode"})
    rows.append({"metric": "fact_rows", "value": len(fact), "detail": "Rows in fact_service_events"})
    rows.append({"metric": "duplicate_event_ids", "value": int(fact["event_id"].duplicated().sum()) if "event_id" in fact else "n/a", "detail": "Duplicate event identifiers after cleaning"})

    if "event_datetime" in fact:
        dt = pd.to_datetime(fact["event_datetime"], errors="coerce")
        rows.append({"metric": "date_start", "value": str(dt.min()), "detail": "Earliest parsed service-event timestamp"})
        rows.append({"metric": "date_end", "value": str(dt.max()), "detail": "Latest parsed service-event timestamp"})
        rows.append({"metric": "missing_event_datetime_pct", "value": _pct(dt.isna().mean()), "detail": "Missing or unparsed event timestamps"})

    for col, detail in [
        ("zone_id", "Zone/beat coverage"),
        ("normalized_service_category", "Service category coverage"),
        ("temperature_2m", "Weather join coverage"),
        ("latitude", "Latitude availability"),
        ("longitude", "Longitude availability"),
    ]:
        if col in fact:
            rows.append({"metric": f"missing_{col}_pct", "value": _pct(fact[col].isna().mean()), "detail": detail})
            if col in {"zone_id", "normalized_service_category"}:
                rows.append({"metric": f"distinct_{col}", "value": int(fact[col].nunique(dropna=True)), "detail": detail})

    if zone_hour is not None and not zone_hour.empty:
        rows.append({"metric": "zone_hour_rows", "value": len(zone_hour), "detail": "Rows in zone-hour feature table"})
        rows.append({"metric": "high_demand_rate_pct", "value": _pct(zone_hour.get("high_demand_flag", pd.Series(dtype=float)).mean()), "detail": "Share of observed zone-hours above zone-specific threshold"})

    for col in fact.columns:
        miss = fact[col].isna().mean()
        if miss > 0:
            rows.append({"metric": f"column_missingness:{col}", "value": _pct(miss), "detail": "Column-level missingness"})

    quality = pd.DataFrame(rows)
    quality.to_csv(output_csv, index=False)

    md_lines = [
        "# Data Quality Notes",
        "",
        "The pipeline records row counts, missingness, duplicate identifiers, date coverage, zone coverage, category coverage, and weather/geography coverage. These checks are intended to make the portfolio analysis credible without overstating what public operational metadata can support.",
        "",
        f"- Sample mode: `{sample_mode}`",
        f"- Fact rows: `{len(fact):,}`",
    ]
    if "zone_id" in fact:
        md_lines.append(f"- Distinct zones/beats: `{fact['zone_id'].nunique(dropna=True):,}`")
    if "normalized_service_category" in fact:
        md_lines.append(f"- Distinct normalized categories: `{fact['normalized_service_category'].nunique(dropna=True):,}`")
    if "temperature_2m" in fact:
        md_lines.append(f"- Weather join coverage: `{_pct(fact['temperature_2m'].notna().mean())}%`")
    md_lines.extend(
        [
            "",
            "Important caveat: missing coordinates or unmapped zones are retained with quality flags when possible, because operational workload analytics can still use timestamp, category, and zone-level metadata.",
        ]
    )
    output_md.write_text("\n".join(md_lines), encoding="utf-8")
    return quality
