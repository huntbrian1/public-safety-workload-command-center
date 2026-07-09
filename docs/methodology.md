# Methodology

## Data Ingestion

The pipeline validates service-event metadata, hourly weather, beat/zone lookup data, and beat/zone GeoJSON. Validation records file sizes, readability, and detected columns.

## Schema Detection

Raw call columns are mapped to canonical analytical fields such as event ID, event timestamp, initial/final call type, service category, disposition, beat, sector, precinct, latitude, and longitude. Missing fields are logged and nullable placeholders are created where possible.

## Cleaning

The call cleaner parses timestamps, standardizes text fields, normalizes categories, cleans coordinates, creates zone identifiers, audits duplicate event IDs, and writes model-ready outputs.

## Weather, Calendar, And Geography Integration

Weather is joined to service-demand records by hourly timestamp. Calendar features include weekday, month, quarter, season, weekend, holiday, business-hour, and after-hours flags. Geography uses beat/zone lookup metadata and mapped beat polygons where available.
`n
## PySpark Feature Engineering

PySpark aggregates cleaned service events to a zone-hour planning grain. Zone-hour features include target demand, weather context, lagged demand, rolling demand, prior-week demand, category mix shares, and high-demand flags.

## Clustering

KMeans groups zones into business-facing operational demand profiles based on workload volume, volatility, weekend/after-hours share, category concentration, weather sensitivity proxy, peak concentration, and monthly variability.

## Machine Learning

Baseline, Random Forest, and MLP comparison models evaluate high-demand zone-hour classification. The model outputs are framed as aggregate planning signals, not individual-event predictions.

## Reporting

The public presentation layer is the Streamlit workload command center. Excel-ready outputs and generated charts/memos support stakeholder review and scenario planning.
