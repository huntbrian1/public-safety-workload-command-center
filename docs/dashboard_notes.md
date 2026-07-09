# Dashboard Notes

## Product Positioning

The Streamlit dashboard is a public safety workload command center. It presents service-demand intelligence for planning, timing, geography, service categories, weather context, and QA lineage. It avoids crime prediction, enforcement optimization, and individual-level claims.

## Presentation Redesign

The dashboard now prioritizes a portfolio-grade first screen:

- Dark command-center hero header with proof badges.
- Compact `Filters & Scenario View` expander with `YYYY-MM` start/end period controls and All / Weekday / Weekend scenario filtering.
- Operational KPI cards only: raw/source records, selected service demand, selected zone-hour records, active zones/beats, selected date range, top workload zone, peak demand hour, and mapped beat polygons.
- First-screen hero visual: `Mapped Beat Workload Coverage`, with a large tile-free Plotly polygon map, visible service-demand color key, top-zone workload bar chart, peak-window insight, and compact PySpark proof card.
- Zone-hour workload heatmap remains a major planning visual below the map.
- Daily Demand Rhythm and Weekly Workload Pattern respond to the period and weekday/weekend filters.
- Service Category Mix is lower on the page and clearly labeled as sample-based.
- Weather-Context Demand is lower on the page, descriptive only, and uses the compact two-panel vertical bar style for precipitation and temperature context while documenting the 25.15% weather-join coverage.
- QA / Data Lineage stays near the bottom and contains the Spark, Java, duplicate-row, and weather-coverage proof details.

## Asset Layer

The dashboard reads app-ready assets from `data/app/` and does not load the full 6.47M-row fact table during normal page rendering.

Generated assets:

- `data/app/dashboard_kpis.json`
- `data/app/zone_summary.csv`
- `data/app/zone_summary_by_period.csv`
- `data/app/map_zone_demand_by_period.csv`
- `data/app/hourly_demand.csv`
- `data/app/day_of_week_demand.csv`
- `data/app/day_hour_heatmap.csv`
- `data/app/service_category_mix.csv`
- `data/app/weather_context_summary.csv`
- `data/app/qa_lineage.json`

Build command:

```powershell
python -u src/dashboard/build_dashboard_assets.py
```

Run command:

```powershell
streamlit run src/dashboard/app.py
```

## Period Filtering

The global time filter uses `YYYY-MM` periods generated from the Spark zone-hour planning layer.

Supported by the period filter:

- Executive KPI demand totals and zone-hour records
- Mapped beat workload shading
- Top workload zones
- Peak demand hour
- Zone-hour heatmap
- Hourly demand rhythm
- Weekly workload pattern
- Weather-context demand

Static or sample-based views:

- Service Category Mix is based on `fact_service_events_sample.csv`; its period filter is sample-based and labeled in the app.
- PySpark proof, Java runtime, duplicate-row QA, and weather-coverage lineage are stable run metadata, not scenario-filtered metrics.

## Stable Spark Lineage

The dashboard preserves the stable PySpark full-transform proof from `outputs/memo/pyspark_processing_report.md`:

- Spark version: `4.1.2`
- Java version: `OpenJDK 17.0.18`
- Run mode full: `True`
- Pandas fallback used: `False`
- Input cleaned call rows: `6,471,140`
- Fact output rows: `6,471,289`
- Zone-hour output rows: `3,952,207`
- Number of zones/beats: `156`
- Weather join coverage: `25.15%`

## QA Limitation

Post-enrichment QA found `149` duplicate fact rows across `6.47M` cleaned events. Unique event IDs matched the cleaned input exactly, with no missing or newly created event IDs. This is documented as a minor enrichment-join limitation.

The duplicate impact is about `0.0023%` of unique event IDs.

## Map Rendering Fix

The Seattle beat GeoJSON uses projected local coordinates. The dashboard reprojects those polygons from EPSG:2926 to WGS84 and renders a tile-free Plotly polygon map for reliable browser and PDF export.

The map renders 55 matched beat polygons. The complete analytic planning layer contains 156 zones/beats, so the section is intentionally labeled as mapped coverage rather than the full analytic layer.

## Map Key

The mapped beat coverage section includes a visible color key. The gradient represents total service demand by mapped beat, from lower demand on the left to higher demand on the right. Grey polygons indicate unmatched beats or no mapped demand in the current asset layer.
