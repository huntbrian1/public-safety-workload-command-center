from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

import pandas as pd

from src import config


CANONICAL_CANDIDATES = {
    "event_id": ["cad_event_number", "event_number", "event_id", "incident_number", "cad_number"],
    "event_datetime": [
        "cad_event_original_time_queued",
        "original_time_queued",
        "event_datetime",
        "call_datetime",
        "datetime",
        "created_at",
        "cad_event_arrived_time",
    ],
    "event_date": ["event_date", "date", "call_date", "occurred_date"],
    "call_type": ["call_type", "call_type_indicator", "type"],
    "initial_call_type": ["initial_call_type", "initial_type", "initial_event_type"],
    "final_call_type": ["final_call_type", "final_type", "final_event_type"],
    "service_category": [
        "event_group",
        "cad_event_response_category",
        "call_type_received_classification",
        "service_category",
        "category",
    ],
    "disposition": ["cad_event_clearance_description", "disposition", "clearance_description", "final_disposition"],
    "beat": ["dispatch_beat", "beat", "zone", "zone_id"],
    "sector": ["dispatch_sector", "sector"],
    "precinct": ["dispatch_precinct", "precinct", "first_precinct"],
    "latitude": ["dispatch_latitude", "latitude", "lat"],
    "longitude": ["dispatch_longitude", "longitude", "lon", "lng"],
    "neighborhood": ["dispatch_neighborhood", "neighborhood"],
    "reporting_area": ["dispatch_reporting_area", "reporting_area"],
}


def normalize_column_name(name: str) -> str:
    text = str(name).strip().lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


def detect_schema(columns: Iterable[str]) -> dict[str, str | None]:
    original_by_norm = {normalize_column_name(col): col for col in columns}
    mapping: dict[str, str | None] = {}

    for canonical, candidates in CANONICAL_CANDIDATES.items():
        selected = None
        for candidate in candidates:
            if candidate in original_by_norm:
                selected = original_by_norm[candidate]
                break
        if selected is None:
            for norm, original in original_by_norm.items():
                if any(candidate in norm for candidate in candidates):
                    selected = original
                    break
        mapping[canonical] = selected

    return mapping


def add_canonical_columns(df: pd.DataFrame, mapping: dict[str, str | None]) -> pd.DataFrame:
    out = df.copy()
    for canonical, source in mapping.items():
        if source is not None and source in out.columns:
            out[canonical] = out[source]
        elif canonical not in out.columns:
            out[canonical] = pd.NA
    return out


def write_schema_report(
    columns: Iterable[str],
    mapping: dict[str, str | None],
    output_path: Path | None = None,
) -> Path:
    if output_path is None:
        output_path = config.MEMO_OUTPUT_DIR / "schema_detection_report.md"
    config.ensure_directories()
    missing = [field for field, source in mapping.items() if source is None]
    lines = [
        "# Schema Detection Report",
        "",
        "This report maps the raw service-event metadata columns to canonical analytical fields.",
        "",
        "## Canonical Mapping",
        "",
        "| Canonical field | Raw column |",
        "|---|---|",
    ]
    for field, source in mapping.items():
        lines.append(f"| `{field}` | `{source or 'MISSING'}` |")
    lines.extend(
        [
            "",
            "## Missing Canonical Fields",
            "",
            ", ".join(f"`{field}`" for field in missing) if missing else "No canonical fields were missing.",
            "",
            "## Raw Columns",
            "",
        ]
    )
    lines.extend(f"- `{column}`" for column in columns)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path
