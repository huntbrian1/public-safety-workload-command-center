PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS fact_service_events (
  event_id TEXT,
  event_datetime TEXT,
  weather_hour TEXT,
  event_date TEXT,
  event_hour INTEGER,
  weekday INTEGER,
  weekday_name TEXT,
  month INTEGER,
  month_name TEXT,
  quarter INTEGER,
  year INTEGER,
  season TEXT,
  is_weekend INTEGER,
  is_holiday INTEGER,
  is_business_hour INTEGER,
  is_after_hours INTEGER,
  zone_id TEXT,
  beat TEXT,
  sector TEXT,
  precinct TEXT,
  latitude REAL,
  longitude REAL,
  initial_call_type TEXT,
  final_call_type TEXT,
  normalized_service_category TEXT,
  disposition TEXT,
  temperature_2m REAL,
  relative_humidity_2m REAL,
  precipitation REAL,
  rain REAL,
  snowfall REAL,
  weather_code REAL,
  wind_speed_10m REAL,
  data_quality_flag TEXT,
  demand_count INTEGER
);

CREATE TABLE IF NOT EXISTS dim_date AS SELECT DISTINCT event_date, weekday, weekday_name, month, month_name, quarter, year, season, is_weekend, is_holiday FROM fact_service_events WHERE 0;
CREATE TABLE IF NOT EXISTS dim_location AS SELECT DISTINCT zone_id, beat, sector, precinct, latitude, longitude FROM fact_service_events WHERE 0;
CREATE TABLE IF NOT EXISTS dim_service_category AS SELECT DISTINCT normalized_service_category FROM fact_service_events WHERE 0;
CREATE TABLE IF NOT EXISTS dim_weather_hour AS SELECT DISTINCT weather_hour, temperature_2m, relative_humidity_2m, precipitation, rain, snowfall, weather_code, wind_speed_10m FROM fact_service_events WHERE 0;

CREATE TABLE IF NOT EXISTS zone_hour_features (
  zone_id TEXT,
  date TEXT,
  date_hour TEXT,
  hour INTEGER,
  weekday INTEGER,
  month INTEGER,
  quarter INTEGER,
  is_weekend INTEGER,
  is_holiday INTEGER,
  is_business_hour INTEGER,
  is_after_hours INTEGER,
  temperature_2m REAL,
  relative_humidity_2m REAL,
  precipitation REAL,
  rain REAL,
  snowfall REAL,
  weather_code REAL,
  wind_speed_10m REAL,
  lag_1_hour_demand REAL,
  lag_24_hour_demand REAL,
  rolling_7_day_avg REAL,
  prior_week_same_hour_demand REAL,
  category_mix_top_1_share REAL,
  category_mix_top_3_share REAL,
  target_demand_count INTEGER,
  high_demand_flag INTEGER
);

CREATE TABLE IF NOT EXISTS cluster_profiles (
  zone_id TEXT,
  cluster_id INTEGER,
  cluster_name TEXT,
  avg_hourly_demand REAL,
  weekend_share REAL,
  after_hours_share REAL,
  demand_volatility REAL,
  weather_sensitivity_proxy REAL
);

CREATE TABLE IF NOT EXISTS model_predictions (
  zone_id TEXT,
  date_hour TEXT,
  actual_high_demand INTEGER,
  baseline_prediction INTEGER,
  ml_prediction INTEGER,
  predicted_high_demand_probability REAL,
  workload_risk_score REAL
);

CREATE TABLE IF NOT EXISTS product_service_recommendations (
  recommendation_id TEXT,
  recommendation_theme TEXT,
  target_user TEXT,
  evidence_signal TEXT,
  product_service_opportunity TEXT,
  priority TEXT
);
