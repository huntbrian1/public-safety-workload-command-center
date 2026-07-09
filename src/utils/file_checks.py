from __future__ import annotations

from pathlib import Path


def human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024 or unit == "TB":
            return f"{size:,.2f} {unit}"
        size /= 1024
    return f"{num_bytes:,} B"


def describe_file(path: Path) -> dict:
    exists = path.exists()
    stat = path.stat() if exists else None
    return {
        "path": str(path),
        "exists": exists,
        "size_bytes": stat.st_size if stat else None,
        "size_readable": human_size(stat.st_size) if stat else None,
        "last_modified": stat.st_mtime if stat else None,
    }
