# Methodology

## Data Ingestion

The pipeline validates four local files: service-event metadata, hourly weather, beat/zone lookup CSV, and beat/zone GeoJSON. Validation records file sizes, readability, and detected columns.

## Schema Detection

Raw call columns are mapped to canonical analytical fields such as event ID, event timestamp, initial/final call type, service category, disposition, beat, sector, precinct, latitude, and longitude. Missing fields are logged and nullable placeholders are created where possible.

## Cleaning

The call cleaner parses timestamps, standardizes text fields, normalizes categories, cleans coordinates, creates zone identifiers, drops duplicate event IDs, and writes Parquet plus a preview CSV.

## Weather, Calendar, and Geography Integration

Weather is parsed from an Open-Meteo style CSV and joined to service events by hourly timestamp. Calendar features include weekday, month, quarter, season, weekend, holiday, business-hour, and after-hours flags. Geography uses beat/zone lookup and, when available, GeoJSON centroids.

## SQLite Modeling

Cleaned outputs are loaded into SQLite tables and indexed by date, hour, zone, and category. SQL query exports support demand, workload risk, category concentration, peak windows, and data quality analysis.

## Feature Engineering

Zone-hour features include target demand, weather context, lagged demand, rolling demand, prior-week demand, category mix shares, and a zone-specific high-demand flag.

## Clustering

KMeans groups zones into business-facing operational demand profiles based on workload volume, volatility, weekend/after-hours share, category concentration, weather sensitivity proxy, peak concentration, and monthly variability.

## Machine Learning

Baseline and Random Forest models predict high-demand zone-hours. An MLP comparison is included when practical and evaluated honestly against simpler methods.

## Reporting

Outputs are created for Hex, Tableau, Excel, Streamlit, SQL review, executive memos, and static charts.
