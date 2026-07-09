from __future__ import annotations

import os
from pathlib import Path


def main() -> None:
    try:
        import boto3
    except ImportError as exc:
        raise SystemExit("Install boto3 to use this helper: pip install boto3") from exc

    bucket = os.environ.get("S3_BUCKET")
    prefix = os.environ.get("S3_PREFIX", "public-safety-demand-intelligence")
    if not bucket:
        raise SystemExit("Set S3_BUCKET before running.")
    root = Path(__file__).resolve().parents[2]
    s3 = boto3.client("s3")
    for path in (root / "outputs").rglob("*"):
        if path.is_file():
            key = f"{prefix}/{path.relative_to(root).as_posix()}"
            s3.upload_file(str(path), bucket, key)
            print(f"uploaded s3://{bucket}/{key}")


if __name__ == "__main__":
    main()
