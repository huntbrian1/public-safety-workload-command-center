# Public Safety Service Demand Intelligence Platform

A portfolio-grade analytics platform that turns large-scale public safety service-event records into workload visibility, zone-hour demand patterns, timing insights, geographic coverage views, and resource-planning signals.

**Live dashboard:** https://public-safety-workload-command-center-apzhvl2n7whz269ys79sns.streamlit.app/

## What This Project Shows

This project demonstrates the kind of data and operations analytics work used in public-sector technology, service operations, and client-facing planning roles:

- Consolidated service-event, weather, calendar, and geographic metadata into an analytics-ready workflow.
- Processed `6,471,140` cleaned service events into `3,952,207` zone-hour planning records.
- Used PySpark for the full-scale zone-hour transformation and aggregation layer.
- Built a Streamlit command-center dashboard for workload timing, mapped beat coverage, service-category mix, and weather-context demand.
- Created modeling workflows for zone segmentation and high-demand period classification.
- Exported Excel-ready outputs for stakeholder reporting and scenario planning.

## Business Problem

Public safety agencies generate high-volume service-demand metadata across timestamps, locations, categories, dispositions, and external conditions. The raw records are difficult to use directly for resource planning, operational reporting, or service-design conversations.

This platform answers:

1. Where and when does service demand concentrate?
2. Which beats/zones show the highest workload intensity?
3. What hours and weekdays create recurring demand peaks?
4. Which service categories shape operational workload?
5. How can historical demand patterns support planning visibility without making individual-level or enforcement-oriented claims?

## Dashboard Highlights

The public Streamlit dashboard is built as a **public safety workload command center**, not a crime map.

Key views include:

- Executive KPI strip for source scale, cleaned events, zone-hour records, active zones/beats, top workload zone, and peak demand hour.
- Mapped Beat Workload Coverage using 55 matched Seattle beat polygons, with a clear color key and coverage note.
- Zone-hour workload heatmap for comparing demand intensity by beat and hour.
- Hourly and weekly demand rhythm charts with month-range and weekday/weekend filters.
- Service-category mix and weather-context demand views.
- Methodology and data QA notes documenting the full PySpark run and known data limitations.

## Data Scale And Lineage

- Raw source records audited: `10.93M`
- Cleaned event-level records: `6,471,140`
- PySpark zone-hour records: `3,952,207`
- Active analytic zones/beats: `156`
- Mapped GeoJSON beat polygons: `55`
- Dashboard date range: `2009-06-02` to `2026-07-04`

The dashboard uses committed, app-ready assets in `data/app/`, so the public app loads quickly without pulling raw source files or rebuilding the full pipeline.

## Methods

The workflow combines:

- Python data cleaning and feature engineering
- PySpark full-scale aggregation to zone-hour planning grain
- Calendar, weather, and geography enrichment
- KMeans clustering of existing beats/zones into workload-profile segments
- Random Forest and MLP model comparison for high-demand period classification
- Streamlit and Plotly for interactive portfolio presentation
- Excel-ready exports for reporting workflows

## Responsible Framing

This project is framed around public-sector operations analytics and service-demand intelligence. It focuses on workload visibility, planning, timing, geography, and product/service recommendations. It does **not** claim to predict individual incidents, optimize enforcement, or make person-level decisions.

## Repository Guide

Important public files:

- `streamlit_app.py` - Streamlit Community Cloud entrypoint
- `src/dashboard/app.py` - dashboard application
- `src/dashboard/build_dashboard_assets.py` - app asset builder
- `data/app/` - committed dashboard assets used by the public app
- `src/processing/spark_transform.py` - PySpark transformation path
- `src/models/` - clustering and demand-model training scripts
- `src/reporting/` - Excel, chart, and memo builders
- `docs/` - methodology, limitations, dashboard notes, and project framing

Raw source files, `.env`, Parquet outputs, model binaries, and local work folders are intentionally ignored.

## Run The Dashboard Locally

```powershell
python -m pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Limitations

Public metadata can contain missing timestamps, missing coordinates, inconsistent categories, and geography mismatches. Weather-context views are descriptive only because weather coverage is limited to the available weather-history overlap. Mapped beat coverage includes 55 matched polygons, while the analytic planning layer contains 156 zones/beats.
