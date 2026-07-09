# Data Dictionary

## fact_service_events

Canonical service-event fact table with event ID, timestamp, date/hour/calendar fields, zone/beat/sector/precinct, coordinates, call type fields, normalized service category, disposition, weather features, data-quality flag, and demand count.

## zone_hour_features

Aggregated zone-hour modeling table with demand target, calendar flags, weather features, lagged demand, rolling demand, prior-week demand, category mix shares, and high-demand flag.

## cluster_profiles

Zone-level clustering output with cluster ID, business-facing cluster name, workload volume, weekend/after-hours shares, category concentration, volatility, weather sensitivity proxy, peak concentration, monthly variability, and PCA coordinates.

## model_predictions

High-demand planning output with zone, date-hour, actual high-demand label, baseline prediction, ML prediction, predicted probability, and workload-risk score.

## Dashboard App Assets

- `dashboard_kpis.json`: executive KPI and lineage values.
- `zone_summary.csv`: all-time zone-level workload summary.
- `zone_summary_by_period.csv`: month-level zone summaries used by dashboard filters.
- `map_zone_demand_by_period.csv`: period-aware map demand asset.
- `hourly_demand.csv`: hour-of-day demand by period and weekday/weekend flag.
- `day_of_week_demand.csv`: weekday demand by period.
- `day_hour_heatmap.csv`: zone-hour workload intensity asset.
- `service_category_mix.csv`: sampled service-category mix asset.
- `weather_context_summary.csv`: weather-joined demand bands.
- `seattle_police_beats.geojson`: mapped beat polygons used by the public dashboard.

## Excel Workbook Tabs

1. Instructions
2. Executive KPIs
3. Zone Summary
4. Forecast Output
5. Capacity Assumptions
6. Scenario Planner
7. Recommendations
8. Data Quality Notes
