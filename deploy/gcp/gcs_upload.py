from __future__ import annotations

import os
from pathlib import Path


def main() -> None:
    try:
        from google.cloud import storage
    except ImportError as exc:
        raise SystemExit("Install google-cloud-storage to use this helper.") from exc

    bucket_name = os.environ.get("GCS_BUCKET")
    prefix = os.environ.get("GCS_PREFIX", "public-safety-demand-intelligence")
    if not bucket_name:
        raise SystemExit("Set GCS_BUCKET before running.")
    root = Path(__file__).resolve().parents[2]
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    for path in (root / "outputs").rglob("*"):
        if path.is_file():
            blob = bucket.blob(f"{prefix}/{path.relative_to(root).as_posix()}")
            blob.upload_from_filename(str(path))
            print(f"uploaded gs://{bucket_name}/{blob.name}")


if __name__ == "__main__":
    main()
