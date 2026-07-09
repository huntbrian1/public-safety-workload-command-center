# Data Dictionary

## fact_service_events

Canonical service-event fact table with event ID, timestamp, date/hour/calendar fields, zone/beat/sector/precinct, coordinates, call type fields, normalized service category, disposition, weather features, data-quality flag, and demand count.

## zone_hour_features

Aggregated zone-hour modeling table with demand target, calendar flags, weather features, lagged demand, rolling demand, prior-week demand, category mix shares, and high-demand flag.

## cluster_profiles

Zone-level clustering output with cluster ID, business-facing cluster name, workload volume, weekend/after-hours shares, category concentration, volatility, weather sensitivity proxy, peak concentration, monthly variability, and PCA coordinates.

## model_predictions

High-demand forecast output with zone, date-hour, actual high-demand label, baseline prediction, ML prediction, predicted probability, and workload-risk score.

## Hex Output Files

- `hex_hourly_demand.csv`: demand by weekday and hour.
- `hex_zone_summary.csv`: zone-level workload summary and risk score.
- `hex_category_summary.csv`: service category demand and share.
- `hex_cluster_profiles.csv`: cluster labels and features.
- `hex_model_predictions.csv`: high-demand model output.
- `hex_recommendations.csv`: product/service recommendations.
- `hex_data_quality_summary.csv`: quality metrics.
- `hex_executive_kpis.csv`: executive KPI strip.
- `hex_weather_demand_summary.csv`: demand by weather context.
- `hex_workload_risk_scores.csv`: risk score export.

## Tableau Output Files

Tableau files mirror Hex outputs and add `tableau_geo_map.csv` for map-ready geography.

## Excel Workbook Tabs

1. Instructions
2. Executive KPIs
3. Zone Summary
4. Forecast Output
5. Capacity Assumptions
6. Scenario Planner
7. Recommendations
8. Data Quality Notes
