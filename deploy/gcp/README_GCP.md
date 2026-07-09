# GCP Deployment Notes

The local pipeline does not require GCP. Use these files only for publishing outputs or deploying the Streamlit app.

## Upload Outputs to Google Cloud Storage

1. Install `google-cloud-storage`.
2. Authenticate with `gcloud auth application-default login` or a service account outside this repo.
3. Set `GCS_BUCKET` and optionally `GCS_PREFIX`.
4. Run `python deploy/gcp/gcs_upload.py`.

## Cloud Run

Build a container image, push it to Artifact Registry or Container Registry, and adapt `cloud_run_service.example.yaml`.

No credentials or secrets are included.
