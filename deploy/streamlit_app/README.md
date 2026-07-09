# Streamlit Cloud Deployment Package

This folder is the lightweight Streamlit Community Cloud app package.

Use `app.py` as the deployed app entrypoint and keep dependency resolution inside this directory. The dashboard reads prebuilt assets from `data/app/` and does not run Spark or load raw project data at runtime.

PySpark remains part of the full local project pipeline in the repository root.