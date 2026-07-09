from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd

from src import config
from src.utils.logging_utils import get_logger
from src.utils.schema_detection import add_canonical_columns, detect_schema, write_schema_report

logger = get_logger(__name__)


def _parse_datetime(series: pd.Series) -> pd.Series:
    text = series.astype("string").str.strip()
    parsed = pd.to_datetime(text, errors="coerce", format="%m/%d/%Y %I:%M:%S %p")
    for fmt in ("%Y %b %d %I:%M:%S %p", "%Y-%m-%d %H:%M:%S"):
        missing = parsed.isna() & text.notna()
        if not missing.any():
            break
        parsed.loc[missing] = pd.to_datetime(text.loc[missing], errors="coerce", format=fmt)
    missing = parsed.isna() & text.notna()
    if missing.any():
        parsed.loc[missing] = pd.to_datetime(text.loc[missing], errors="coerce")
    return parsed


def _clean_text(series: pd.Series) -> pd.Series:
    return (
        series.astype("string")
        .str.strip()
        .str.replace(r"\s+", " ", regex=True)
        .replace({"": pd.NA, "nan": pd.NA, "<NA>": pd.NA})
    )


def _normalize_service_category(row: pd.Series) -> str:
    candidates = [
        row.get("service_category"),
        row.get("final_call_type"),
        row.get("initial_call_type"),
        row.get("call_type"),
    ]
    for value in candidates:
        if pd.notna(value) and str(value).strip():
            text = str(value).strip()
            text = re.sub(r"\s*-\s*", " - ", text)
            text = re.sub(r"\s+", " ", text)
            return text.title()
    return "Uncategorized"


def _normalize_service_category_frame(out: pd.DataFrame) -> pd.Series:
    values = pd.Series(pd.NA, index=out.index, dtype="string")
    for col in ["service_category", "final_call_type", "initial_call_type", "call_type"]:
        if col in out:
            values = values.fillna(out[col].astype("string").str.strip())
    values = (
        values.fillna("Uncategorized")
        .astype("string")
        .str.replace(r"\s*-\s*", " - ", regex=True)
        .str.replace(r"\s+", " ", regex=True)
        .str.title()
    )
    return values.replace({"": "Uncategorized", "<Na>": "Uncategorized"})


def clean_frame(df: pd.DataFrame, mapping: dict[str, str | None] | None = None, dedupe_event_id: bool = True) -> pd.DataFrame:
    if mapping is None:
        mapping = detect_schema(df.columns)
    out = add_canonical_columns(df, mapping)

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

    out["event_datetime"] = _parse_datetime(out["event_datetime"])
    if out["event_id"].isna().all():
        out["event_id"] = "generated_" + pd.Series(range(len(out)), index=out.index).astype(str)

    out["latitude"] = pd.to_numeric(out["latitude"].astype("string").str.replace(",", "", regex=False), errors="coerce")
    out["longitude"] = pd.to_numeric(out["longitude"].astype("string").str.replace(",", "", regex=False), errors="coerce")
    out["beat"] = out["beat"].str.upper()
    out["sector"] = out["sector"].str.upper()
    out["precinct"] = out["precinct"].str.upper()
    out["zone_id"] = out["beat"].fillna("UNKNOWN")
    out["normalized_service_category"] = _normalize_service_category_frame(out)

    flags = []
    flags.append(out["event_datetime"].isna().map({True: "missing_datetime", False: ""}))
    flags.append(out["zone_id"].isna().map({True: "missing_zone", False: ""}))
    flags.append(out["normalized_service_category"].eq("Uncategorized").map({True: "missing_category", False: ""}))
    out["data_quality_flag"] = pd.concat(flags, axis=1).agg(lambda row: ";".join([x for x in row if x]) or "ok", axis=1)

    keep_cols = [
        "event_id",
        "event_datetime",
        "call_type",
        "initial_call_type",
        "final_call_type",
        "service_category",
        "normalized_service_category",
        "disposition",
        "zone_id",
        "beat",
        "sector",
        "precinct",
        "latitude",
        "longitude",
        "neighborhood",
        "reporting_area",
        "data_quality_flag",
    ]
    out = out[[col for col in keep_cols if col in out.columns]]
    if dedupe_event_id:
        out = out.drop_duplicates(subset=["event_id"], keep="first")
    return out


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _add_selection_rank(cleaned: pd.DataFrame, source_row_start: int) -> pd.DataFrame:
    out = cleaned.copy()
    out["source_row_number"] = range(source_row_start, source_row_start + len(out))
    score_cols = [
        "event_datetime",
        "zone_id",
        "beat",
        "sector",
        "precinct",
        "latitude",
        "longitude",
        "normalized_service_category",
        "disposition",
    ]
    out["record_completeness_score"] = out[[c for c in score_cols if c in out.columns]].notna().sum(axis=1).astype("int16")
    timestamp_rank = out["event_datetime"].astype("int64", copy=False) // 1_000_000_000
    timestamp_rank = timestamp_rank.where(timestamp_rank > 0, 0).astype("int64")
    source_rank = out["source_row_number"].astype("int64")
    out["event_timestamp_rank"] = timestamp_rank
    out["record_selection_rank"] = (
        out["record_completeness_score"].astype("int64") * 10_000_000_000_000_000
        + out["event_timestamp_rank"].astype("int64") * 10_000_000
        + source_rank
    )
    return out


def _load_duplicate_metadata():
    audit_path = config.PROCESSED_DIR / "duplicate_event_audit.parquet"
    if not audit_path.exists():
        return None
    try:
        import dask.dataframe as dd

        audit = dd.read_parquet(str(audit_path))[["event_id", "duplicate_group_size", "duplicate_reason"]].rename(
            columns={"duplicate_group_size": "duplicate_count"}
        )
        audit["event_id"] = audit["event_id"].astype(str)
        return audit
    except Exception as exc:
        logger.warning("Duplicate audit metadata could not be loaded: %s", exc)
        return None


def _global_collapse_cleaned_events(temp_path: Path) -> tuple[int, int, int]:
    try:
        import dask.dataframe as dd
    except ImportError as exc:
        raise RuntimeError("Full-mode global duplicate collapse requires dask in this local runtime.") from exc

    ddf = dd.read_parquet(str(temp_path))
    pre_collapse_rows = int(ddf.shape[0].compute())
    ddf["event_id"] = ddf["event_id"].astype(str)
    duplicate_metadata = _load_duplicate_metadata()
    if duplicate_metadata is not None:
        ddf = ddf.merge(duplicate_metadata, on="event_id", how="left")
    else:
        ddf["duplicate_count"] = 1
        ddf["duplicate_reason"] = "duplicate_audit_not_available"

    ddf["duplicate_count"] = ddf["duplicate_count"].fillna(1).astype("int64")
    ddf["duplicate_reason"] = ddf["duplicate_reason"].fillna("not_duplicated")
    ddf["has_duplicate_history"] = ddf["duplicate_count"] > 1
    ddf["duplicate_collapse_rule"] = "max(record_completeness_score, event_datetime, source_row_number)"

    best_rank = ddf.groupby("event_id")["record_selection_rank"].max().reset_index()
    collapsed = ddf.merge(best_rank, on=["event_id", "record_selection_rank"], how="inner")
    collapsed = collapsed.drop_duplicates(subset=["event_id"], keep="first")
    collapsed = collapsed.drop(columns=[c for c in ["event_timestamp_rank", "record_selection_rank"] if c in collapsed.columns])

    _remove_path(config.CLEANED_CALLS_PARQUET)
    collapsed.to_parquet(str(config.CLEANED_CALLS_PARQUET), engine="pyarrow", write_index=False)
    final_rows = int(dd.read_parquet(str(config.CLEANED_CALLS_PARQUET)).shape[0].compute())
    collapsed.head(5000).to_csv(config.CLEANED_CALLS_PREVIEW, index=False)
    duplicate_groups = int(duplicate_metadata.shape[0].compute()) if duplicate_metadata is not None else 0
    return pre_collapse_rows, final_rows, duplicate_groups


def clean_calls() -> None:
    config.ensure_directories()
    started = datetime.now()
    logger.info("Reading call data from %s", config.CALL_DATA_PATH)
    sample_n = config.SAMPLE_ROWS if config.SAMPLE_MODE else None
    first = pd.read_csv(config.CALL_DATA_PATH, nrows=1000, low_memory=False)
    mapping = detect_schema(first.columns)
    write_schema_report(first.columns, mapping)
    logger.info("Schema mapping: %s", mapping)
    usecols = sorted({source for source in mapping.values() if source is not None})

    if config.SAMPLE_MODE:
        df = pd.read_csv(config.CALL_DATA_PATH, nrows=sample_n, usecols=usecols, low_memory=False)
        cleaned = clean_frame(df, mapping)
        cleaned.to_parquet(config.CLEANED_CALLS_PARQUET, index=False)
        cleaned.head(5000).to_csv(config.CLEANED_CALLS_PREVIEW, index=False)
        _write_clean_report(started, datetime.now(), len(df), len(cleaned), 0, mode="sample")
        logger.info("Wrote %s rows to %s", len(cleaned), config.CLEANED_CALLS_PARQUET)
        return

    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError("Full mode requires pyarrow. Install requirements or run sample mode.") from exc

    temp_path = config.INTERIM_DIR / "cleaned_call_events_all_rows.parquet"
    _remove_path(temp_path)
    writer = None
    total = 0
    raw_total = 0
    preview_written = False
    try:
        for chunk_idx, chunk in enumerate(pd.read_csv(config.CALL_DATA_PATH, chunksize=250_000, usecols=usecols, low_memory=False)):
            source_row_start = raw_total + 1
            raw_total += len(chunk)
            cleaned = clean_frame(chunk, mapping, dedupe_event_id=False)
            cleaned = _add_selection_rank(cleaned, source_row_start)
            table = pa.Table.from_pandas(cleaned, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(temp_path, table.schema)
            writer.write_table(table)
            total += len(cleaned)
            if not preview_written:
                cleaned.head(5000).to_csv(config.CLEANED_CALLS_PREVIEW, index=False)
                preview_written = True
            logger.info("Processed chunk %s; cumulative rows=%s", chunk_idx, total)
    finally:
        if writer is None:
            logger.warning("No chunks were written from %s", config.CALL_DATA_PATH)
        else:
            writer.close()
    pre_collapse_rows, final_rows, duplicate_groups = _global_collapse_cleaned_events(temp_path)
    duplicate_total = pre_collapse_rows - final_rows
    _write_clean_report(
        started,
        datetime.now(),
        raw_total,
        final_rows,
        duplicate_total,
        mode="full",
        pre_collapse_rows=pre_collapse_rows,
        duplicate_groups=duplicate_groups,
    )
    logger.info("Wrote full cleaned call dataset with %s globally collapsed rows", final_rows)


def _write_clean_report(
    started: datetime,
    ended: datetime,
    raw_rows: int,
    cleaned_rows: int,
    duplicate_rows: int,
    mode: str,
    pre_collapse_rows: int | None = None,
    duplicate_groups: int | None = None,
) -> None:
    elapsed = (ended - started).total_seconds()
    lines = [
        "# Clean Calls Report",
        "",
        f"- Run mode: `{mode}`",
        f"- Sample mode config: `{config.SAMPLE_MODE}`",
        f"- Started: `{started.isoformat(timespec='seconds')}`",
        f"- Ended: `{ended.isoformat(timespec='seconds')}`",
        f"- Elapsed seconds: `{elapsed:,.1f}`",
        f"- Raw rows read: `{raw_rows:,}`",
        f"- Pre-collapse cleaned rows: `{pre_collapse_rows:,}`" if pre_collapse_rows is not None else "- Pre-collapse cleaned rows: `n/a`",
        f"- Cleaned rows written: `{cleaned_rows:,}`",
        f"- Duplicate rows collapsed globally: `{duplicate_rows:,}`",
        f"- Duplicate event-ID groups from audit: `{duplicate_groups:,}`" if duplicate_groups is not None else "- Duplicate event-ID groups from audit: `n/a`",
        "- Collapse rule: `max(record_completeness_score, event_datetime, source_row_number)`",
        "- Duplicate history fields retained: `duplicate_count`, `has_duplicate_history`, `duplicate_reason`, `duplicate_collapse_rule`",
        f"- Output: `{config.CLEANED_CALLS_PARQUET}`",
    ]
    (config.MEMO_OUTPUT_DIR / "clean_calls_report.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    clean_calls()
