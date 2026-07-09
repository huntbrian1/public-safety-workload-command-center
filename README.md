# Public Safety Service Demand Intelligence Platform

End-to-end portfolio analytics project for public safety service-demand intelligence, operational workload forecasting, command-center visibility, and product/service analytics.

This project consolidates large service-event metadata with weather, calendar, and geographic zone metadata; cleans and structures the data; builds a SQLite analytics layer; creates PySpark-compatible transformations; trains clustering and demand models; and exports Tableau-ready, Excel-ready, and Streamlit-ready outputs.

## Motorola Solutions Alignment

The project is framed for a Business Operations Analyst / data analytics role that values large-scale data consolidation, actionable insight generation, product/service recommendations, stakeholder communication, and machine learning applied responsibly to operational metadata.

It demonstrates:

- Diverse source consolidation: call/service metadata, weather, calendar, and beat/zone geography.
- Business analytics: workload-risk scoring, demand concentration analysis, category mix reporting, and executive KPIs.
- Data engineering: local raw/interim/processed zones, schema detection, Parquet, SQLite, and repeatable scripts.
- Machine learning: zone clustering, baseline forecasting, Random Forest high-demand prediction, and MLP comparison.
- Reporting: Tableau-ready CSVs, Excel scenario planner, Streamlit app, and generated memos.
- Technical depth: PySpark path, R validation, Docker, Kubernetes, AWS, and GCP support files.

## Business Problem

Public safety agencies produce large volumes of service-event metadata across timestamps, zones, categories, dispositions, weather, and geography. These records can be fragmented and hard to translate into operational workload visibility or product/service recommendations.

This platform answers:

1. Where and when does public safety service demand concentrate?
2. Which service categories create the highest operational workload?
3. Can historical metadata predict high-demand zone-hour periods?
4. Can beats/zones be clustered into useful operational demand profiles?
5. What dashboard, alerting, workload scoring, and scenario-planning features could support public safety clients?

## Expected Data Paths

```text
data/raw/seattle_call_data_full.csv
data/external/seattle_weather_hourly_2021_2025.csv
data/external/seattle_police_beats.csv
data/external/seattle_police_beats.geojson
```

The first working version runs locally from manually downloaded files. Sample mode is enabled by default so the 6 GB call file can be processed quickly.

## Architecture

```text
Raw CSV/GeoJSON
  -> validation + schema detection
  -> cleaned Parquet / cleaned lookup CSVs
  -> calendar + weather + geography joins
  -> fact_service_events + zone_hour_features
  -> SQLite analytics layer
  -> Tableau CSVs
  -> clustering + high-demand prediction + MLP comparison
  -> Excel planner + Streamlit app + memos/charts
  -> optional PySpark, R, Docker, Kubernetes, AWS, GCP
```

## Setup

Recommended local setup:

```powershell
git clone <your-repo-url>
cd public-safety-workload-command-center
python -m pip install -r requirements.txt
```

Or create a conda environment:

```powershell
conda env create -f environment.yml
conda activate public-safety-service-demand-intelligence
```

## Streamlit Dashboard

The dashboard is a polished public safety workload command center built on period-aware app assets in `data/app/`. It does not load the full 6.47M-row fact table during normal page rendering.

Build dashboard assets:

```powershell
python -u src/dashboard/build_dashboard_assets.py
```

Launch the dashboard:

```powershell
streamlit run streamlit_app.py
```

Dashboard sections include:

- Dark command-center hero header and proof badges.
- `Filters & Scenario View` controls for `YYYY-MM` start/end periods plus All / Weekday / Weekend scenario filtering.
- Operational KPI cards for raw/source records, selected service demand, selected zone-hour records, active zones/beats, selected date range, top workload zone, peak demand hour, and mapped beat polygons.
- First-screen `Mapped Beat Workload Coverage` hero section with a visible map key, 55 matched Seattle beat polygons, a top-zone workload bar chart, peak-window insight, and compact PySpark proof card.
- Zone-hour workload intensity heatmap, hourly demand rhythm, weekly workload pattern, sample-based service category mix, weather-context demand, and bottom QA / Data Lineage.
- Tile-free Plotly polygon map rendering after EPSG:2926 to WGS84 reprojection. The map is labeled as mapped coverage because the GeoJSON covers 55 matched polygons while the analytic planning layer contains 156 zones/beats.

Period filtering is supported by the Spark zone-hour planning assets for the map, top zones, KPI demand totals, heatmap, hourly rhythm, weekly workload pattern, and weather-context charts. Service-category mix is sample-based from `fact_service_events_sample.csv` and is labeled accordingly.

Stable PySpark lineage is preserved from `outputs/memo/pyspark_processing_report.md`: Spark `4.1.2`, OpenJDK `17.0.18`, full mode `True`, pandas fallback `False`, `6,471,140` cleaned input events, `6,471,289` fact rows, and `3,952,207` zone-hour rows. The known `149` post-enrichment duplicate fact rows are documented as a minor enrichment-join QA limitation with no missing or fake event IDs.

More detail is in `docs/dashboard_notes.md`.

## Public Streamlit Deployment

This repository is prepared for Streamlit Community Cloud with the full dashboard asset layer committed under `data/app/`.

Suggested app entrypoint:

```text
streamlit_app.py
```

The public app includes the dashboard CSV/JSON assets and beat GeoJSON needed for the command-center view. Raw source files, `.env`, SQLite databases, Parquet outputs, model binaries, local work folders, and secret files remain ignored.

## Run Locally

PowerShell commands:

```powershell
$env:SAMPLE_MODE="true"
$env:SAMPLE_ROWS="500000"
python -m src.ingest.validate_local_files
python -m src.processing.clean_calls
python -m src.processing.clean_weather
python -m src.processing.clean_geography
python -m src.processing.build_features
python -m src.database.load_sqlite
python -m src.database.run_sqlite_queries
python -m src.models.train_cluster_model
python -m src.models.train_demand_model
python -m src.models.train_deep_learning_model
python -m src.reporting.build_tableau_outputs
python -m src.reporting.build_excel_planner
```

If `make` is available:

```bash
make validate-data
make process
make sqlite
make model
make report
make excel
```

## Sample Mode vs Full Mode

Sample mode reads the first `SAMPLE_ROWS` rows from the large call file and is ideal for portfolio iteration. Full mode processes the file in chunks and writes Parquet row groups; use it when the local machine has enough disk and runtime.

Configure with:

```powershell
$env:SAMPLE_MODE="false"
```

## SQLite Layer

SQLite is the local analytics layer at:

```text
data/processed/public_safety_ops.sqlite
```

Tables include `fact_service_events`, `dim_date`, `dim_location`, `dim_service_category`, `dim_weather_hour`, `zone_hour_features`, `cluster_profiles`, `model_predictions`, and `product_service_recommendations`.

## PySpark

`src/processing/spark_transform.py` demonstrates scalable zone-hour aggregation. If PySpark is unavailable, it writes a clear report and uses a local pandas fallback so the portfolio remains runnable without paid infrastructure.


## Modeling

- Baseline: prior-week same-hour demand and historical high-demand threshold.
- Traditional ML: Random Forest classifier over calendar, weather, lagged demand, category mix, and zone features.
- Deep learning comparison: sklearn MLP classifier where practical.
- Clustering: KMeans zone segmentation with business-facing cluster names.

Outputs and honest evaluation notes are written to `outputs/models/` and `outputs/memo/`.

## Reporting Outputs

- Tableau: `outputs/tableau/`
- Excel scenario planner: `outputs/excel/public_safety_scenario_planner.xlsx`
- Charts: `outputs/charts/`
- Memos: `outputs/memo/`

## Streamlit App

```powershell
streamlit run streamlit_app.py
```

The public dashboard reads the committed `data/app/` assets so it can run without rebuilding the full pipeline.

## Docker

```bash
docker compose up --build
```

Docker Compose includes the Streamlit app. SQLite remains file-based and mounted through `data/`.

## Kubernetes, AWS, and GCP

Deployment files are realistic support artifacts, not requirements for local execution:

- Kubernetes manifests: `deploy/kubernetes/`
- AWS support: `deploy/aws/`
- GCP support: `deploy/gcp/`

Credentials and secrets are intentionally excluded.

## Limitations

Public metadata can contain missing timestamps, missing coordinates, inconsistent categories, and geography mismatches. Weather joins assume local hourly timestamps. Forecasts are aggregate planning aids for workload visibility and should not be used for individual-level decisions.

## Next Steps

- Run full mode on the complete dataset and compare results against sample mode.
- Add richer event/calendar context if available.
- Validate geography joins with authoritative zone definitions.
- Publish the Tableau workbook using generated CSVs.
- Add CI checks for schema detection and core pipeline execution.

## Resume Bullets

- Built a public safety service-demand analytics platform using Python, SQLite, PySpark, Streamlit, Tableau-ready outputs, and Excel to clean, integrate, and analyze large-scale service-event metadata.
- Developed clustering and ML workflows to segment zones, identify demand drivers, and forecast high-volume service periods.
- Created Streamlit and Excel reporting tools translating workload-risk indicators into product/service and resource-planning recommendations.
