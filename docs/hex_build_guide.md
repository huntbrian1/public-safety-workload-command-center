# Hex Build Guide

## CSVs to Upload

Upload all files from `outputs/hex/`:

- `hex_hourly_demand.csv`
- `hex_zone_summary.csv`
- `hex_category_summary.csv`
- `hex_cluster_profiles.csv`
- `hex_model_predictions.csv`
- `hex_recommendations.csv`
- `hex_data_quality_summary.csv`
- `hex_executive_kpis.csv`
- `hex_weather_demand_summary.csv`
- `hex_workload_risk_scores.csv`

## Dashboard Sections

1. Executive Summary
2. Data Integration & Quality
3. Demand Trends
4. Zone/Beat Workload Profiles
5. Cluster Analysis
6. High-Demand Forecasting
7. Product & Service Recommendations
8. Limitations & Next Steps

## Suggested Hex SQL Cells

```sql
SELECT weekday_name, event_hour, SUM(demand_count) AS demand_count
FROM hex_hourly_demand
GROUP BY weekday_name, event_hour;
```

```sql
SELECT zone_id, workload_risk_score, total_events, avg_hourly_demand
FROM hex_zone_summary
ORDER BY workload_risk_score DESC
LIMIT 20;
```

```sql
SELECT normalized_service_category, demand_count, share_of_total
FROM hex_category_summary
ORDER BY demand_count DESC
LIMIT 15;
```

```sql
SELECT cluster_name, COUNT(*) AS zone_count, AVG(avg_hourly_demand) AS avg_hourly_demand
FROM hex_cluster_profiles
GROUP BY cluster_name
ORDER BY avg_hourly_demand DESC;
```

```sql
SELECT zone_id, AVG(predicted_high_demand_probability) AS avg_predicted_probability
FROM hex_model_predictions
GROUP BY zone_id
ORDER BY avg_predicted_probability DESC
LIMIT 20;
```

```sql
SELECT precipitation_flag, temperature_bucket, AVG(avg_demand) AS avg_demand
FROM hex_weather_demand_summary
GROUP BY precipitation_flag, temperature_bucket
ORDER BY temperature_bucket;
```

```sql
SELECT metric, value, detail
FROM hex_data_quality_summary;
```

## Suggested Python Cells

```python
import pandas as pd
zone = hex_zone_summary.copy()
zone["risk_rank"] = zone["workload_risk_score"].rank(ascending=False)
zone.head(10)
```

```python
recs = hex_recommendations.sort_values(["priority", "recommendation_id"])
recs[["recommendation_theme", "evidence_signal", "product_service_opportunity"]]
```

## Chart Plan

- KPI cards from `hex_executive_kpis.csv`.
- Heatmap from `hex_hourly_demand.csv`.
- Bar chart of top workload-risk zones.
- Category mix bar chart.
- Cluster profile comparison.
- Forecast table of high predicted probability zone-hours.
- Recommendation table grouped by priority.
- Data quality notes table.

## Motorola-Aligned Commentary

Use language such as service-demand intelligence, operational workload, command-center visibility, product/service recommendations, client service analytics, and resource-planning intelligence.

Avoid enforcement-oriented wording. Keep the analysis focused on aggregate workload visibility and product/service planning.
