-- name: demand_by_hour_weekday
SELECT weekday_name, event_hour, COUNT(*) AS demand_count
FROM fact_service_events
GROUP BY weekday_name, event_hour
ORDER BY weekday, event_hour;

-- name: demand_by_month
SELECT year, month, month_name, COUNT(*) AS demand_count
FROM fact_service_events
GROUP BY year, month, month_name
ORDER BY year, month;

-- name: demand_by_zone
SELECT zone_id, precinct, sector, COUNT(*) AS demand_count
FROM fact_service_events
GROUP BY zone_id, precinct, sector
ORDER BY demand_count DESC;

-- name: demand_by_service_category
SELECT normalized_service_category, COUNT(*) AS demand_count
FROM fact_service_events
GROUP BY normalized_service_category
ORDER BY demand_count DESC;

-- name: top_demand_zones
SELECT zone_id, COUNT(*) AS demand_count
FROM fact_service_events
GROUP BY zone_id
ORDER BY demand_count DESC
LIMIT 25;

-- name: peak_demand_windows
SELECT weekday_name, event_hour, COUNT(*) AS demand_count
FROM fact_service_events
GROUP BY weekday_name, event_hour
ORDER BY demand_count DESC
LIMIT 25;

-- name: weekend_vs_weekday_demand
SELECT is_weekend, COUNT(*) AS demand_count
FROM fact_service_events
GROUP BY is_weekend;

-- name: business_vs_after_hours_demand
SELECT is_after_hours, COUNT(*) AS demand_count
FROM fact_service_events
GROUP BY is_after_hours;

-- name: weather_and_demand_relationship
SELECT
  ROUND(temperature_2m, 0) AS temperature_bucket,
  CASE WHEN precipitation > 0 THEN 'precipitation_observed' ELSE 'no_precipitation' END AS precipitation_flag,
  COUNT(*) AS demand_count
FROM fact_service_events
GROUP BY temperature_bucket, precipitation_flag
ORDER BY temperature_bucket;

-- name: zone_category_concentration
SELECT zone_id, normalized_service_category, COUNT(*) AS demand_count
FROM fact_service_events
GROUP BY zone_id, normalized_service_category
ORDER BY zone_id, demand_count DESC;

-- name: demand_volatility_by_zone
SELECT zone_id, AVG(target_demand_count) AS avg_hourly_demand,
       AVG(target_demand_count * target_demand_count) - AVG(target_demand_count) * AVG(target_demand_count) AS demand_variance
FROM zone_hour_features
GROUP BY zone_id
ORDER BY demand_variance DESC;

-- name: monthly_trend
SELECT year, month, COUNT(*) AS demand_count
FROM fact_service_events
GROUP BY year, month
ORDER BY year, month;

-- name: workload_risk_score_by_zone
SELECT zone_id,
       AVG(target_demand_count) AS avg_hourly_demand,
       AVG(high_demand_flag) AS high_demand_rate,
       AVG(is_after_hours) AS after_hours_share,
       AVG(is_weekend) AS weekend_share
FROM zone_hour_features
GROUP BY zone_id
ORDER BY high_demand_rate DESC, avg_hourly_demand DESC;

-- name: top_forecasted_high_demand_zones
SELECT zone_id, AVG(predicted_high_demand_probability) AS avg_predicted_probability, AVG(workload_risk_score) AS avg_workload_risk_score
FROM model_predictions
GROUP BY zone_id
ORDER BY avg_predicted_probability DESC
LIMIT 25;

-- name: cluster_profile_summary
SELECT cluster_id, cluster_name, COUNT(*) AS zone_count, AVG(avg_hourly_demand) AS avg_hourly_demand, AVG(after_hours_share) AS after_hours_share
FROM cluster_profiles
GROUP BY cluster_id, cluster_name
ORDER BY avg_hourly_demand DESC;

-- name: data_quality_summary
SELECT data_quality_flag, COUNT(*) AS row_count
FROM fact_service_events
GROUP BY data_quality_flag
ORDER BY row_count DESC;
