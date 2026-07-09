from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src import config
from src.utils.file_checks import describe_file
from src.utils.logging_utils import get_logger


logger = get_logger(__name__)


def _sample_columns(path: Path) -> tuple[bool, list[str], str | None]:
    try:
        if path.suffix.lower() == ".geojson":
            with path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
            features = payload.get("features", [])
            columns = sorted(features[0].get("properties", {}).keys()) if features else []
            return True, columns, f"Feature count: {len(features):,}"
        try:
            df = pd.read_csv(path, nrows=5, low_memory=False)
        except Exception:
            skiprows = 0
            with path.open("r", encoding="utf-8-sig", errors="replace") as f:
                for idx, line in enumerate(f):
                    if line.lower().startswith("time,"):
                        skiprows = idx
                        break
            df = pd.read_csv(path, skiprows=skiprows, nrows=5, low_memory=False)
        return True, list(df.columns), f"Sample rows read: {len(df):,}"
    except Exception as exc:
        return False, [], str(exc)


def validate() -> Path:
    config.ensure_directories()
    report_path = config.MEMO_OUTPUT_DIR / "data_file_validation.md"
    lines = [
        "# Data File Validation",
        "",
        "Required local files are checked before processing. The source files can be manually downloaded and placed in the expected data paths.",
        "",
        "| Dataset | Path | Exists | Size | Readable | Notes |",
        "|---|---|---:|---:|---:|---|",
    ]

    missing = []
    for name, path in config.REQUIRED_FILES.items():
        info = describe_file(path)
        readable, columns, note = _sample_columns(path) if info["exists"] else (False, [], "Missing file")
        if not info["exists"]:
            missing.append(path)
        lines.append(
            f"| {name} | `{path}` | {info['exists']} | {info['size_readable'] or 'n/a'} | {readable} | {note or ''} |"
        )
        logger.info("%s exists=%s readable=%s size=%s", name, info["exists"], readable, info["size_readable"])
        if columns:
            logger.info("%s columns: %s", name, columns)
            lines.append("")
            lines.append(f"## {name} Columns")
            lines.extend(f"- `{col}`" for col in columns)
            lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    if missing:
        raise FileNotFoundError("Missing required files: " + ", ".join(str(p) for p in missing))
    logger.info("Validation report written to %s", report_path)
    return report_path


if __name__ == "__main__":
    validate()
