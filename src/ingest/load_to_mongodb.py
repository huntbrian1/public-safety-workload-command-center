from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

from src import config
from src.utils.file_checks import describe_file
from src.utils.logging_utils import get_logger
from src.utils.schema_detection import detect_schema

logger = get_logger(__name__)


RAW_ATLAS_LIMIT = 100_000


def _masked_mongo_host(uri: str) -> str:
    try:
        parsed = urlparse(uri)
        return parsed.hostname or "unknown-host"
    except Exception:
        return "unknown-host"


def _count_csv_rows(path: Path) -> int:
    total = 0
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024 * 16), b""):
            total += block.count(b"\n")
    return max(total - 1, 0)


def _parquet_rows(path: Path) -> int | None:
    try:
        import pyarrow.dataset as ds

        return ds.dataset(path, format="parquet").count_rows()
    except Exception:
        return None


def _clean_records(df: pd.DataFrame, load_tag: str) -> list[dict]:
    clean = df.where(pd.notna(df), None)
    records = clean.to_dict(orient="records")
    for record in records:
        record["_pipeline_load_tag"] = load_tag
        record["_loaded_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    return records


def load_to_mongodb() -> None:
    config.ensure_directories()
    started = datetime.now()
    report = ["# MongoDB Atlas Load Report", ""]
    try:
        from pymongo import MongoClient, UpdateOne
    except Exception as exc:
        raise RuntimeError("pymongo and dnspython are required for MongoDB Atlas loading.") from exc

    if not config.MONGO_URI or "mongodb+srv://" not in config.MONGO_URI:
        raise RuntimeError("MONGO_URI is missing or is not an Atlas mongodb+srv URI. Put it in .env; do not commit .env.")

    host = _masked_mongo_host(config.MONGO_URI)
    load_tag = "full-run-" + datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    raw_inserted_or_modified = 0
    metadata_count = 0
    indexes_created: list[str] = []

    try:
        client = MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=15_000, connectTimeoutMS=15_000)
        client.admin.command("ping")
        db = client[config.MONGO_DB]
        raw_coll = db[config.MONGO_COLLECTION]
        meta_coll = db["pipeline_run_metadata"]

        sample = pd.read_csv(config.CALL_DATA_PATH, nrows=1000, low_memory=False)
        schema_mapping = detect_schema(sample.columns)
        event_id_col = schema_mapping.get("event_id") or "CAD Event Number"
        datetime_col = schema_mapping.get("event_datetime")
        beat_col = schema_mapping.get("beat")

        for field in [event_id_col, datetime_col, beat_col, "_pipeline_load_tag"]:
            if field:
                raw_coll.create_index(field)
                indexes_created.append(f"raw_call_events.{field}")
        meta_coll.create_index("run_tag", unique=True)
        meta_coll.create_index("created_at")
        indexes_created.extend(["pipeline_run_metadata.run_tag", "pipeline_run_metadata.created_at"])

        remaining = RAW_ATLAS_LIMIT
        for chunk in pd.read_csv(config.CALL_DATA_PATH, chunksize=5_000, nrows=RAW_ATLAS_LIMIT, low_memory=False):
            records = _clean_records(chunk, load_tag)
            operations = []
            for idx, record in enumerate(records):
                key = record.get(event_id_col)
                if key is None:
                    key = hashlib.sha256(f"{load_tag}-{raw_inserted_or_modified}-{idx}".encode()).hexdigest()
                    record["_generated_key"] = key
                operations.append(UpdateOne({event_id_col: key}, {"$set": record}, upsert=True))
            if operations:
                result = raw_coll.bulk_write(operations, ordered=False)
                raw_inserted_or_modified += result.upserted_count + result.modified_count + result.matched_count
            remaining -= len(records)
            logger.info("Atlas raw representative load progress: %s/%s", RAW_ATLAS_LIMIT - remaining, RAW_ATLAS_LIMIT)
            if remaining <= 0:
                break

        raw_rows = _count_csv_rows(config.CALL_DATA_PATH)
        fact_rows = _parquet_rows(config.FACT_EVENTS_PARQUET)
        zone_hour_rows = _parquet_rows(config.ZONE_HOUR_FEATURES_PARQUET)
        metadata = {
            "run_tag": load_tag,
            "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "sample_mode": config.SAMPLE_MODE,
            "raw_row_count": raw_rows,
            "cleaned_fact_row_count": fact_rows,
            "zone_hour_row_count": zone_hour_rows,
            "schema_mapping": schema_mapping,
            "source_files": {name: describe_file(path) for name, path in config.REQUIRED_FILES.items()},
            "raw_representative_document_limit": RAW_ATLAS_LIMIT,
            "raw_representative_documents_loaded": raw_inserted_or_modified,
            "notes": "SQLite and PySpark process the full dataset locally; Atlas stores a representative raw/semi-structured subset plus full-run metadata for portfolio demonstration and free-tier practicality.",
        }
        meta_coll.update_one({"run_tag": load_tag}, {"$set": metadata}, upsert=True)
        metadata_count = 1
        client.close()
    except Exception:
        # Let the caller see the real failure. The report below is only written on success.
        raise

    ended = datetime.now()
    report.extend(
        [
            f"- Atlas ping succeeded: `True`",
            f"- Masked Atlas host: `{host}`",
            f"- Database: `{config.MONGO_DB}`",
            f"- Raw collection: `{config.MONGO_COLLECTION}`",
            "- Metadata collection: `pipeline_run_metadata`",
            f"- Inserted/updated representative raw document operations: `{raw_inserted_or_modified:,}`",
            f"- Inserted/updated metadata documents: `{metadata_count:,}`",
            f"- Capped raw load limit: `{RAW_ATLAS_LIMIT:,}`",
            "- Capped-load reason: Atlas stores representative raw records plus full-run metadata; full local processing is handled by SQLite/PySpark to avoid unnecessary free-tier cost and runtime.",
            f"- Indexes created/verified: `{', '.join(indexes_created)}`",
            f"- Started: `{started.isoformat(timespec='seconds')}`",
            f"- Ended: `{ended.isoformat(timespec='seconds')}`",
            f"- Elapsed seconds: `{(ended - started).total_seconds():,.1f}`",
        ]
    )
    (config.MEMO_OUTPUT_DIR / "mongodb_load_report.md").write_text("\n".join(report), encoding="utf-8")


if __name__ == "__main__":
    load_to_mongodb()
