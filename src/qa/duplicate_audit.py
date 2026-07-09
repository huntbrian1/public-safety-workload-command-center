from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd
from pandas.util import hash_pandas_object

from src import config
from src.processing.clean_calls import _clean_text, _normalize_service_category_frame, _parse_datetime
from src.utils.schema_detection import add_canonical_columns, detect_schema


QA_OUTPUT_DIR = config.OUTPUT_DIR / "qa"
DUPLICATE_AUDIT_PARQUET = config.PROCESSED_DIR / "duplicate_event_audit.parquet"
DUPLICATE_SAMPLE_CSV = QA_OUTPUT_DIR / "duplicate_event_samples.csv"
DUPLICATE_REPORT = config.MEMO_OUTPUT_DIR / "duplicate_audit_report.md"

COMPARISON_FIELDS = [
    "event_id",
    "queued_datetime",
    "zone_id",
    "beat",
    "sector",
    "precinct",
    "latitude",
    "longitude",
    "call_type",
    "initial_call_type",
    "final_call_type",
    "service_category",
    "normalized_service_category",
    "disposition",
]

HASH_FAMILIES = {
    "raw": "raw_row_hash",
    "core": "core_comparison_hash",
    "timestamp": "timestamp_comparison_hash",
    "location": "location_comparison_hash",
    "category": "category_comparison_hash",
    "disposition": "disposition_comparison_hash",
}


def _row_count_parquet(path: Path) -> int:
    import pyarrow.dataset as ds

    return ds.dataset(path, format="parquet").count_rows()


def _find_mapping() -> tuple[dict[str, str | None], list[str]]:
    first = pd.read_csv(config.CALL_DATA_PATH, nrows=1000, low_memory=False)
    return detect_schema(first.columns), list(first.columns)


def _count_event_ids(event_id_col: str, chunksize: int = 1_000_000) -> tuple[int, Counter[str]]:
    counts: Counter[str] = Counter()
    raw_rows = 0
    for chunk_idx, chunk in enumerate(
        pd.read_csv(
            config.CALL_DATA_PATH,
            usecols=[event_id_col],
            chunksize=chunksize,
            dtype=str,
            keep_default_na=False,
            na_filter=False,
            low_memory=False,
        )
    ):
        ids = chunk[event_id_col].astype(str).str.strip()
        raw_rows += len(ids)
        counts.update(ids.tolist())
        print(f"duplicate audit count pass chunk={chunk_idx} raw_rows={raw_rows:,}", flush=True)
    return raw_rows, counts


def _canonicalize_for_audit(raw: pd.DataFrame, mapping: dict[str, str | None], source_event_id: pd.Series) -> pd.DataFrame:
    out = add_canonical_columns(raw, mapping)
    for col in [
        "event_id",
        "call_type",
        "initial_call_type",
        "final_call_type",
        "service_category",
        "disposition",
        "beat",
        "sector",
        "precinct",
        "neighborhood",
        "reporting_area",
    ]:
        if col in out:
            out[col] = _clean_text(out[col])
    out["event_id"] = source_event_id.astype(str).str.strip().to_numpy()
    out["queued_datetime"] = _parse_datetime(out["event_datetime"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    out["latitude"] = pd.to_numeric(out["latitude"].astype("string").str.replace(",", "", regex=False), errors="coerce").round(6)
    out["longitude"] = pd.to_numeric(out["longitude"].astype("string").str.replace(",", "", regex=False), errors="coerce").round(6)
    out["beat"] = out["beat"].str.upper()
    out["sector"] = out["sector"].str.upper()
    out["precinct"] = out["precinct"].str.upper()
    out["zone_id"] = out["beat"].fillna("UNKNOWN")
    out["normalized_service_category"] = _normalize_service_category_frame(out)
    for col in COMPARISON_FIELDS:
        if col not in out:
            out[col] = pd.NA
    return out[COMPARISON_FIELDS]


def _hash_fields(df: pd.DataFrame, cols: list[str]) -> pd.Series:
    text = df[cols].astype("string").fillna("<NA>")
    return hash_pandas_object(text, index=False).astype("uint64").astype(str)


def _append_hashes(audit: pd.DataFrame, raw: pd.DataFrame, raw_columns: list[str]) -> pd.DataFrame:
    out = audit.copy()
    out["raw_row_hash"] = hash_pandas_object(raw[raw_columns].astype("string").fillna("<NA>"), index=False).astype("uint64").astype(str)
    out["core_comparison_hash"] = _hash_fields(out, COMPARISON_FIELDS)
    out["timestamp_comparison_hash"] = _hash_fields(out, ["queued_datetime"])
    out["location_comparison_hash"] = _hash_fields(out, ["zone_id", "beat", "sector", "precinct", "latitude", "longitude"])
    out["category_comparison_hash"] = _hash_fields(
        out,
        ["call_type", "initial_call_type", "final_call_type", "service_category", "normalized_service_category"],
    )
    out["disposition_comparison_hash"] = _hash_fields(out, ["disposition"])
    return out


def _init_group_state(duplicate_counts: dict[str, int]) -> dict[str, dict[str, object]]:
    return {
        event_id: {
            "duplicate_group_size": int(count),
            "observed_rows_in_audit_pass": 0,
            "first_raw": None,
            "first_core": None,
            "first_timestamp": None,
            "first_location": None,
            "first_category": None,
            "first_disposition": None,
            "raw_diff": False,
            "core_diff": False,
            "timestamp_diff": False,
            "location_diff": False,
            "category_diff": False,
            "disposition_diff": False,
        }
        for event_id, count in duplicate_counts.items()
    }


def _update_family_state(state: dict[str, object], family: str, first_value: str, chunk_unique_count: int) -> None:
    first_key = f"first_{family}"
    diff_key = f"{family}_diff"
    if state[first_key] is None:
        state[first_key] = first_value
    elif state[first_key] != first_value:
        state[diff_key] = True
    if chunk_unique_count > 1:
        state[diff_key] = True


def _build_group_audit(
    mapping: dict[str, str | None],
    raw_columns: list[str],
    duplicate_counts: dict[str, int],
    event_id_col: str,
    chunksize: int = 250_000,
) -> pd.DataFrame:
    states = _init_group_state(duplicate_counts)
    duplicate_ids = set(duplicate_counts)
    row_start = 0
    for chunk_idx, chunk in enumerate(
        pd.read_csv(
            config.CALL_DATA_PATH,
            chunksize=chunksize,
            dtype=str,
            keep_default_na=False,
            na_filter=False,
            low_memory=False,
        )
    ):
        row_start += len(chunk)
        ids = chunk[event_id_col].astype(str).str.strip()
        mask = ids.isin(duplicate_ids)
        if not mask.any():
            print(f"duplicate audit classify pass chunk={chunk_idx} scanned_rows={row_start:,} duplicate_rows=0", flush=True)
            continue
        dup_raw = chunk.loc[mask].copy()
        canonical = _canonicalize_for_audit(dup_raw, mapping, ids.loc[mask])
        audit = _append_hashes(canonical, dup_raw, raw_columns)
        agg_spec = {"event_id": ("event_id", "size")}
        for family, col in HASH_FAMILIES.items():
            agg_spec[f"{family}_first"] = (col, "first")
            agg_spec[f"{family}_nunique"] = (col, "nunique")
        chunk_groups = audit.groupby("event_id", dropna=False).agg(**agg_spec).rename(columns={"event_id": "chunk_rows"})
        for event_id, row in chunk_groups.iterrows():
            state = states[event_id]
            state["observed_rows_in_audit_pass"] = int(state["observed_rows_in_audit_pass"]) + int(row["chunk_rows"])
            for family in HASH_FAMILIES:
                _update_family_state(state, family, str(row[f"{family}_first"]), int(row[f"{family}_nunique"]))
        print(
            f"duplicate audit classify pass chunk={chunk_idx} scanned_rows={row_start:,} duplicate_rows={len(audit):,}",
            flush=True,
        )

    records = []
    for event_id, state in states.items():
        conflict_type_count = int(state["timestamp_diff"]) + int(state["location_diff"]) + int(state["category_diff"]) + int(state["disposition_diff"])
        exact_duplicate_all_fields = not bool(state["raw_diff"])
        same_event_id_identical_core_fields = bool(state["raw_diff"]) and not bool(state["core_diff"])
        possible_event_update_or_history = (
            not exact_duplicate_all_fields and not same_event_id_identical_core_fields and (conflict_type_count > 1 or bool(state["core_diff"]))
        )
        if exact_duplicate_all_fields:
            duplicate_reason = "A. exact_duplicate_all_fields"
        elif same_event_id_identical_core_fields:
            duplicate_reason = "B. same_event_id_identical_core_fields"
        elif conflict_type_count > 1:
            duplicate_reason = "G. possible_event_update_or_history"
        elif state["timestamp_diff"]:
            duplicate_reason = "C. same_event_id_conflicting_timestamp"
        elif state["location_diff"]:
            duplicate_reason = "D. same_event_id_conflicting_location"
        elif state["category_diff"]:
            duplicate_reason = "E. same_event_id_conflicting_category"
        elif state["disposition_diff"]:
            duplicate_reason = "F. same_event_id_conflicting_disposition"
        else:
            duplicate_reason = "G. possible_event_update_or_history"
        records.append(
            {
                "event_id": event_id,
                "duplicate_group_size": int(state["duplicate_group_size"]),
                "observed_rows_in_audit_pass": int(state["observed_rows_in_audit_pass"]),
                "rows_beyond_first": int(state["duplicate_group_size"]) - 1,
                "exact_duplicate_all_fields": exact_duplicate_all_fields,
                "same_event_id_identical_core_fields": same_event_id_identical_core_fields,
                "same_event_id_conflicting_timestamp": bool(state["timestamp_diff"]),
                "same_event_id_conflicting_location": bool(state["location_diff"]),
                "same_event_id_conflicting_category": bool(state["category_diff"]),
                "same_event_id_conflicting_disposition": bool(state["disposition_diff"]),
                "possible_event_update_or_history": possible_event_update_or_history,
                "conflict_type_count": conflict_type_count,
                "duplicate_reason": duplicate_reason,
            }
        )
    return pd.DataFrame.from_records(records)


def _collect_sample_rows(
    mapping: dict[str, str | None],
    raw_columns: list[str],
    group_audit: pd.DataFrame,
    event_id_col: str,
    chunksize: int = 250_000,
) -> pd.DataFrame:
    top_ids = group_audit.sort_values(["duplicate_group_size", "event_id"], ascending=[False, True]).head(20)["event_id"].tolist()
    target_ids = set(top_ids)
    for reason in sorted(group_audit["duplicate_reason"].dropna().unique()):
        ids = group_audit[group_audit["duplicate_reason"].eq(reason)].sort_values("duplicate_group_size", ascending=False).head(10)["event_id"]
        target_ids.update(ids.tolist())

    frames: list[pd.DataFrame] = []
    row_start = 0
    reason_cols = [
        "event_id",
        "duplicate_group_size",
        "duplicate_reason",
        "exact_duplicate_all_fields",
        "same_event_id_identical_core_fields",
        "same_event_id_conflicting_timestamp",
        "same_event_id_conflicting_location",
        "same_event_id_conflicting_category",
        "same_event_id_conflicting_disposition",
        "possible_event_update_or_history",
    ]
    reason_lookup = group_audit[reason_cols]
    for chunk_idx, chunk in enumerate(
        pd.read_csv(
            config.CALL_DATA_PATH,
            chunksize=chunksize,
            dtype=str,
            keep_default_na=False,
            na_filter=False,
            low_memory=False,
        )
    ):
        source_rows = pd.Series(range(row_start + 1, row_start + len(chunk) + 1), index=chunk.index)
        row_start += len(chunk)
        ids = chunk[event_id_col].astype(str).str.strip()
        sample_raw = chunk.loc[ids.isin(target_ids)].copy()
        if sample_raw.empty:
            continue
        canonical = _canonicalize_for_audit(sample_raw, mapping, ids.loc[sample_raw.index])
        audit = _append_hashes(canonical, sample_raw, raw_columns)
        audit["source_row_number"] = source_rows.loc[sample_raw.index].to_numpy()
        audit = audit.merge(reason_lookup, on="event_id", how="left")
        frames.append(audit)
        print(f"duplicate audit sample pass chunk={chunk_idx} sample_rows={sum(len(f) for f in frames):,}", flush=True)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).sort_values(
        ["duplicate_group_size", "event_id", "source_row_number"], ascending=[False, True, True]
    )


def _safe_share(numerator: int | float, denominator: int | float) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


def _write_report(
    started: datetime,
    raw_rows: int,
    cleaned_rows: int,
    current_removed_rows: int,
    group_audit: pd.DataFrame,
) -> None:
    ended = datetime.now()
    duplicate_event_ids = len(group_audit)
    global_rows_in_duplicate_groups = int(group_audit["duplicate_group_size"].sum()) if not group_audit.empty else 0
    global_rows_beyond_first = int(group_audit["rows_beyond_first"].sum()) if not group_audit.empty else 0
    max_rows = int(group_audit["duplicate_group_size"].max()) if not group_audit.empty else 0
    non_exact_removed = int(group_audit.loc[~group_audit["exact_duplicate_all_fields"], "rows_beyond_first"].sum()) if not group_audit.empty else 0
    non_exact_share = _safe_share(non_exact_removed, global_rows_beyond_first)
    conflict_flags = [
        "same_event_id_conflicting_timestamp",
        "same_event_id_conflicting_location",
        "same_event_id_conflicting_category",
        "same_event_id_conflicting_disposition",
        "possible_event_update_or_history",
    ]
    conflicting_removed = int(group_audit.loc[group_audit[conflict_flags].any(axis=1), "rows_beyond_first"].sum()) if not group_audit.empty else 0
    safety_status = (
        "FAIL - current event_id-only collapse is too aggressive"
        if non_exact_share > 0.01 or conflicting_removed > 0
        else "PASS - removed duplicates are overwhelmingly exact"
    )
    reason_counts = (
        group_audit.groupby("duplicate_reason").agg(event_ids=("event_id", "size"), rows_beyond_first=("rows_beyond_first", "sum")).reset_index()
        if not group_audit.empty
        else pd.DataFrame(columns=["duplicate_reason", "event_ids", "rows_beyond_first"])
    )
    flag_rows = []
    for flag in [
        "exact_duplicate_all_fields",
        "same_event_id_identical_core_fields",
        "same_event_id_conflicting_timestamp",
        "same_event_id_conflicting_location",
        "same_event_id_conflicting_category",
        "same_event_id_conflicting_disposition",
        "possible_event_update_or_history",
    ]:
        sub = group_audit[group_audit[flag]] if not group_audit.empty else group_audit
        flag_rows.append(
            {
                "category": flag,
                "event_ids": len(sub),
                "rows_beyond_first": int(sub["rows_beyond_first"].sum()) if not sub.empty else 0,
            }
        )
    flag_counts = pd.DataFrame(flag_rows)
    top20 = group_audit.sort_values(["duplicate_group_size", "event_id"], ascending=[False, True]).head(20)

    lines = [
        "# Duplicate Audit Report",
        "",
        f"- Started: `{started.isoformat(timespec='seconds')}`",
        f"- Ended: `{ended.isoformat(timespec='seconds')}`",
        f"- Elapsed seconds: `{(ended - started).total_seconds():,.1f}`",
        f"- Run mode full: `{not config.SAMPLE_MODE}`",
        "",
        "## Current Cleaner Deduplication Logic",
        "",
        "The current `src/processing/clean_calls.py` logic uses:",
        "",
        "```python",
        'out = out.drop_duplicates(subset=["event_id"], keep="first")',
        "```",
        "",
        "- Deduplication key: `event_id` only.",
        "- Timestamp included in key: `False`.",
        "- Location/category/disposition included in key: `False`.",
        "- All columns included in key: `False`.",
        "- Scope: inside each pandas chunk, not a global whole-file duplicate decision.",
        "",
        "## Counts",
        "",
        f"- Raw row count: `{raw_rows:,}`",
        f"- Current cleaned row count: `{cleaned_rows:,}`",
        f"- Current removed duplicate row count: `{current_removed_rows:,}`",
        f"- Current duplicate percentage: `{_safe_share(current_removed_rows, raw_rows):.2%}`",
        f"- Number of duplicated event IDs globally: `{duplicate_event_ids:,}`",
        f"- Rows in duplicated event-ID groups globally: `{global_rows_in_duplicate_groups:,}`",
        f"- Rows beyond first globally if event ID were collapsed once: `{global_rows_beyond_first:,}`",
        f"- Max rows per duplicated event ID: `{max_rows:,}`",
        "",
        "## Safety Finding",
        "",
        f"- Status: `{safety_status}`",
        f"- Non-exact rows beyond first: `{non_exact_removed:,}`",
        f"- Non-exact share of global rows beyond first: `{non_exact_share:.2%}`",
        f"- Conflicting/update-like rows beyond first: `{conflicting_removed:,}`",
        "",
        "A non-trivial share of same-event-ID rows is treated as unsafe to collapse when duplicate records are not exact all-field duplicates or when timestamp, location, category, or disposition conflicts are present.",
        "",
        "## Duplicate Reason Counts",
        "",
        "| Duplicate reason | Event IDs | Rows beyond first |",
        "|---|---:|---:|",
    ]
    lines.extend(f"| {r.duplicate_reason} | {int(r.event_ids):,} | {int(r.rows_beyond_first):,} |" for r in reason_counts.itertuples(index=False))
    lines.extend(["", "## Overlapping Conflict Flags", "", "| Flag | Event IDs | Rows beyond first |", "|---|---:|---:|"])
    lines.extend(f"| {r.category} | {int(r.event_ids):,} | {int(r.rows_beyond_first):,} |" for r in flag_counts.itertuples(index=False))
    lines.extend(["", "## Top 20 Event IDs By Duplicate Count", "", "| Event ID | Duplicate group size | Duplicate reason |", "|---|---:|---|"])
    lines.extend(
        f"| `{r.event_id}` | {int(r.duplicate_group_size):,} | {r.duplicate_reason} |" for r in top20.itertuples(index=False)
    )
    lines.extend(
        [
            "",
            "## Comparison Fields",
            "",
            "The duplicate classification compared these canonical fields:",
            "",
            *[f"- `{field}`" for field in COMPARISON_FIELDS],
            "",
            "Exact duplicate detection also used a hash of every raw source field in the CSV row.",
            "",
            "## Outputs",
            "",
            f"- Group-level duplicate audit Parquet: `{DUPLICATE_AUDIT_PARQUET}`",
            f"- Duplicate sample CSV: `{DUPLICATE_SAMPLE_CSV}`",
            "",
            "## Recommendation",
            "",
        ]
    )
    if safety_status.startswith("FAIL"):
        lines.append(
            "Do not treat the current cleaned fact table as final. Patch `clean_calls.py` so it preserves duplicate history evidence, adds duplicate-count/history flags to the cleaned event table, and keeps the best record per event ID using a documented rule instead of blindly keeping the first row."
        )
    else:
        lines.append("The existing collapse appears safe based on the duplicate audit, but the audit output should still be retained for traceability.")
    DUPLICATE_REPORT.write_text("\n".join(lines), encoding="utf-8")


def run_duplicate_audit() -> None:
    config.ensure_directories()
    QA_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    started = datetime.now()
    mapping, raw_columns = _find_mapping()
    event_id_col = mapping.get("event_id")
    if not event_id_col:
        raise RuntimeError("Could not identify source event ID column for duplicate audit.")

    raw_rows, id_counts = _count_event_ids(event_id_col)
    duplicate_counts = {event_id: count for event_id, count in id_counts.items() if count > 1}
    del id_counts
    group_audit = _build_group_audit(mapping, raw_columns, duplicate_counts, event_id_col)
    group_audit.to_parquet(DUPLICATE_AUDIT_PARQUET, index=False)

    sample = _collect_sample_rows(mapping, raw_columns, group_audit, event_id_col)
    sample_cols = [
        "event_id",
        "queued_datetime",
        "zone_id",
        "beat",
        "sector",
        "precinct",
        "call_type",
        "initial_call_type",
        "final_call_type",
        "service_category",
        "normalized_service_category",
        "disposition",
        "latitude",
        "longitude",
        "source_row_number",
        "raw_row_hash",
        "core_comparison_hash",
        "timestamp_comparison_hash",
        "location_comparison_hash",
        "category_comparison_hash",
        "disposition_comparison_hash",
        "duplicate_group_size",
        "duplicate_reason",
        "exact_duplicate_all_fields",
        "same_event_id_identical_core_fields",
        "same_event_id_conflicting_timestamp",
        "same_event_id_conflicting_location",
        "same_event_id_conflicting_category",
        "same_event_id_conflicting_disposition",
        "possible_event_update_or_history",
    ]
    if sample.empty:
        pd.DataFrame(columns=sample_cols).to_csv(DUPLICATE_SAMPLE_CSV, index=False)
    else:
        sample[sample_cols].head(5000).to_csv(DUPLICATE_SAMPLE_CSV, index=False)

    cleaned_rows = _row_count_parquet(config.CLEANED_CALLS_PARQUET) if config.CLEANED_CALLS_PARQUET.exists() else 0
    current_removed_rows = raw_rows - cleaned_rows
    _write_report(started, raw_rows, cleaned_rows, current_removed_rows, group_audit)


if __name__ == "__main__":
    run_duplicate_audit()
