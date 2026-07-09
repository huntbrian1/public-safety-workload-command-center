from __future__ import annotations

import shutil
import subprocess
import time
import os
from datetime import datetime
from pathlib import Path

from src import config
from src.processing.build_calendar_features import us_federal_holidays
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


WEATHER_COLS = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "rain",
    "snowfall",
    "weather_code",
    "wind_speed_10m",
]


def _safe_remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _write_single_csv(df, path: Path) -> None:
    tmp_dir = path.with_name(path.stem + "_spark_csv_tmp")
    _safe_remove(tmp_dir)
    _safe_remove(path)
    df.coalesce(1).write.mode("overwrite").option("header", True).csv(str(tmp_dir))
    part_files = list(tmp_dir.glob("part-*.csv"))
    if not part_files:
        raise RuntimeError(f"Spark CSV write did not produce a part file in {tmp_dir}")
    shutil.move(str(part_files[0]), path)
    shutil.rmtree(tmp_dir)


def _java_version() -> str:
    java_home = os.getenv("JAVA_HOME")
    java_exe = Path(java_home) / "bin" / "java.exe" if java_home else None
    cmd = [str(java_exe)] if java_exe and java_exe.exists() else ["java"]
    cmd.append("-version")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        text = (result.stderr or result.stdout).splitlines()
        return text[0] if text else "unknown"
    except Exception as exc:
        return f"unavailable: {exc}"


def _ensure_local_java() -> None:
    java_home_raw = os.getenv("JAVA_HOME")
    conda_prefix = os.getenv("CONDA_PREFIX")
    candidate_home = Path(java_home_raw) if java_home_raw else None
    if (not candidate_home or not candidate_home.exists()) and conda_prefix:
        candidate_home = Path(conda_prefix) / "Library"
    if candidate_home and candidate_home.exists():
        os.environ.setdefault("JAVA_HOME", str(candidate_home))
        java_bin = str(candidate_home / "bin")
        path_parts = os.environ.get("PATH", "").split(os.pathsep)
        if java_bin not in path_parts:
            os.environ["PATH"] = java_bin + os.pathsep + os.environ.get("PATH", "")
    os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
    os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)
    os.environ.setdefault("SPARK_LOCAL_IP", "127.0.0.1")
    os.environ.setdefault("SPARK_DRIVER_BIND_ADDRESS", "127.0.0.1")
    os.environ.setdefault("SPARK_LOCAL_HOSTNAME", "localhost")


def _spark_read_path(path: Path) -> str:
    return path.resolve().as_uri()


def run_spark_transform() -> None:
    config.ensure_directories()
    started = datetime.now()
    start_time = time.time()
    fallback_used = False
    _ensure_local_java()

    try:
        from pyspark.sql import SparkSession, Window
        from pyspark.sql import functions as F
    except Exception as exc:
        raise RuntimeError("PySpark is required for the full-scale phase and could not be imported.") from exc

    spark = (
        SparkSession.builder.appName("public-safety-service-demand-intelligence-full")
        .config("spark.sql.session.timeZone", "America/Los_Angeles")
        .config("spark.sql.shuffle.partitions", "96")
        .config("spark.driver.memory", "6g")
        .config("spark.hadoop.io.native.lib.available", "false")
        .config("spark.sql.parquet.enableVectorizedReader", "false")
        .config("spark.driver.host", "127.0.0.1")
        .config("spark.driver.bindAddress", "127.0.0.1")
        .config("spark.local.hostname", "localhost")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )

    spark_version = spark.version
    java_version = _java_version()
    try:
        print("spark_transform progress: reading cleaned call parquet", flush=True)
        calls = spark.read.parquet(_spark_read_path(config.CLEANED_CALLS_PARQUET))
        print("spark_transform progress: counting cleaned call rows", flush=True)
        input_rows = calls.count()
        if input_rows == 0:
            raise RuntimeError("Cleaned call Parquet has zero rows.")
        print(f"spark_transform progress: cleaned call rows = {input_rows:,}", flush=True)

        print("spark_transform progress: reading cleaned weather parquet", flush=True)
        weather = spark.read.parquet(_spark_read_path(config.CLEANED_WEATHER_PARQUET))
        weather = weather.withColumn("weather_hour", F.date_trunc("hour", F.col("weather_hour")))

        if config.CLEANED_BEATS_CSV.exists():
            print("spark_transform progress: reading cleaned geography csv", flush=True)
            geography = spark.read.option("header", True).csv(_spark_read_path(config.CLEANED_BEATS_CSV))
            geography = geography.select(
                F.upper(F.trim(F.col("zone_id"))).alias("geo_zone_id"),
                F.upper(F.trim(F.col("precinct"))).alias("geo_precinct"),
                F.upper(F.trim(F.col("sector"))).alias("geo_sector"),
            ).dropDuplicates(["geo_zone_id"])
        else:
            geography = None

        years = list(range(2000, 2031))
        holidays = [d.isoformat() for d in us_federal_holidays(years)]

        fact = (
            calls.withColumn("event_datetime", F.to_timestamp("event_datetime"))
            .withColumn("weather_hour", F.date_trunc("hour", F.col("event_datetime")))
            .withColumn("event_date", F.to_date("event_datetime"))
            .withColumn("event_hour", F.hour("event_datetime"))
            .withColumn("weekday", ((F.dayofweek("event_datetime") + F.lit(5)) % F.lit(7)).cast("int"))
            .withColumn("weekday_name", F.date_format("event_datetime", "EEEE"))
            .withColumn("month", F.month("event_datetime"))
            .withColumn("month_name", F.date_format("event_datetime", "MMMM"))
            .withColumn("quarter", F.quarter("event_datetime"))
            .withColumn("year", F.year("event_datetime"))
            .withColumn(
                "season",
                F.when(F.col("month").isin(12, 1, 2), F.lit("Winter"))
                .when(F.col("month").isin(3, 4, 5), F.lit("Spring"))
                .when(F.col("month").isin(6, 7, 8), F.lit("Summer"))
                .otherwise(F.lit("Fall")),
            )
            .withColumn("is_weekend", F.col("weekday").isin(5, 6))
            .withColumn("is_holiday", F.date_format("event_date", "yyyy-MM-dd").isin(holidays))
            .withColumn(
                "is_business_hour",
                (F.col("event_hour").between(8, 17)) & (~F.col("is_weekend")) & (~F.col("is_holiday")),
            )
            .withColumn("is_after_hours", ~F.col("is_business_hour"))
            .withColumn("demand_count", F.lit(1))
            .withColumn("zone_id", F.coalesce(F.col("zone_id"), F.lit("UNKNOWN")))
            .withColumn("beat", F.coalesce(F.col("beat"), F.col("zone_id")))
        )

        if geography is not None:
            fact = fact.join(geography, fact.zone_id == geography.geo_zone_id, "left")
            fact = fact.withColumn("precinct", F.coalesce(F.col("precinct"), F.col("geo_precinct")))
            fact = fact.withColumn("sector", F.coalesce(F.col("sector"), F.col("geo_sector")))
            fact = fact.drop("geo_zone_id", "geo_precinct", "geo_sector")

        fact = fact.join(weather, on="weather_hour", how="left")
        for col in WEATHER_COLS:
            if col not in fact.columns:
                fact = fact.withColumn(col, F.lit(None).cast("double"))

        fact_cols = [
            "event_id",
            "event_datetime",
            "weather_hour",
            "event_date",
            "event_hour",
            "weekday",
            "weekday_name",
            "month",
            "month_name",
            "quarter",
            "year",
            "season",
            "is_weekend",
            "is_holiday",
            "is_business_hour",
            "is_after_hours",
            "zone_id",
            "beat",
            "sector",
            "precinct",
            "latitude",
            "longitude",
            "initial_call_type",
            "final_call_type",
            "normalized_service_category",
            "disposition",
            *WEATHER_COLS,
            "data_quality_flag",
            "demand_count",
        ]
        fact = fact.select(*[F.col(c) if c in fact.columns else F.lit(None).alias(c) for c in fact_cols])

        _safe_remove(config.FACT_EVENTS_PARQUET)
        print("spark_transform progress: writing fact_service_events parquet", flush=True)
        fact.write.mode("overwrite").parquet(str(config.FACT_EVENTS_PARQUET))
        print("spark_transform progress: writing fact_service_events sample csv", flush=True)
        fact.limit(50_000).toPandas().to_csv(config.FACT_EVENTS_SAMPLE_CSV, index=False)

        print("spark_transform progress: aggregating zone-hour features", flush=True)
        group_cols = [
            "zone_id",
            "event_date",
            "event_hour",
            "weekday",
            "month",
            "quarter",
            "is_weekend",
            "is_holiday",
            "is_business_hour",
            "is_after_hours",
        ]
        agg = fact.groupBy(*group_cols).agg(
            F.sum("demand_count").alias("target_demand_count"),
            *[F.avg(c).alias(c) for c in WEATHER_COLS if c != "weather_code"],
            F.first("weather_code", ignorenulls=True).alias("weather_code"),
        )

        cat_counts = fact.groupBy(*group_cols, "normalized_service_category").agg(F.count("*").alias("category_count"))
        total_counts = cat_counts.groupBy(*group_cols).agg(F.sum("category_count").alias("total_count"))
        cat_share = cat_counts.join(total_counts, on=group_cols, how="inner").withColumn(
            "category_share", F.col("category_count") / F.col("total_count")
        )
        cat_window = Window.partitionBy(*group_cols).orderBy(F.desc("category_share"), F.asc("normalized_service_category"))
        cat_ranked = cat_share.withColumn("category_rank", F.row_number().over(cat_window))
        cat_mix = cat_ranked.groupBy(*group_cols).agg(
            F.sum(F.when(F.col("category_rank") <= 1, F.col("category_share")).otherwise(F.lit(0.0))).alias(
                "category_mix_top_1_share"
            ),
            F.sum(F.when(F.col("category_rank") <= 3, F.col("category_share")).otherwise(F.lit(0.0))).alias(
                "category_mix_top_3_share"
            ),
        )

        zone_hour = (
            agg.join(cat_mix, on=group_cols, how="left")
            .withColumnRenamed("event_hour", "hour")
            .withColumn("date", F.col("event_date"))
            .withColumn("date_hour", F.expr("to_timestamp(event_date) + make_interval(0,0,0,0,hour,0,0)"))
        )
        zone_window = Window.partitionBy("zone_id").orderBy("date_hour")
        rolling_window = zone_window.rowsBetween(-168, -1)
        thresholds = zone_hour.groupBy("zone_id").agg(
            F.expr("percentile_approx(target_demand_count, 0.75, 10000)").alias("zone_high_threshold")
        )
        zone_hour = (
            zone_hour.withColumn("lag_1_hour_demand", F.coalesce(F.lag("target_demand_count", 1).over(zone_window), F.lit(0)))
            .withColumn("lag_24_hour_demand", F.coalesce(F.lag("target_demand_count", 24).over(zone_window), F.lit(0)))
            .withColumn("rolling_7_day_avg", F.coalesce(F.avg("target_demand_count").over(rolling_window), F.lit(0.0)))
            .withColumn(
                "prior_week_same_hour_demand",
                F.coalesce(F.lag("target_demand_count", 168).over(zone_window), F.lit(0)),
            )
            .join(thresholds, on="zone_id", how="left")
            .withColumn("high_demand_flag", (F.col("target_demand_count") > F.col("zone_high_threshold")).cast("int"))
            .drop("zone_high_threshold", "event_date")
        )

        final_cols = [
            "zone_id",
            "date",
            "date_hour",
            "hour",
            "weekday",
            "month",
            "quarter",
            "is_weekend",
            "is_holiday",
            "is_business_hour",
            "is_after_hours",
            *WEATHER_COLS,
            "lag_1_hour_demand",
            "lag_24_hour_demand",
            "rolling_7_day_avg",
            "prior_week_same_hour_demand",
            "category_mix_top_1_share",
            "category_mix_top_3_share",
            "target_demand_count",
            "high_demand_flag",
        ]
        zone_hour = zone_hour.select(*final_cols)
        _safe_remove(config.ZONE_HOUR_FEATURES_PARQUET)
        print("spark_transform progress: writing zone_hour_features parquet", flush=True)
        zone_hour.write.mode("overwrite").parquet(str(config.ZONE_HOUR_FEATURES_PARQUET))
        _safe_remove(config.PROCESSED_DIR / "spark_zone_hour_features.parquet")
        print("spark_transform progress: writing spark_zone_hour_features parquet", flush=True)
        zone_hour.write.mode("overwrite").parquet(str(config.PROCESSED_DIR / "spark_zone_hour_features.parquet"))
        print("spark_transform progress: writing zone_hour_features csv", flush=True)
        _write_single_csv(zone_hour, config.ZONE_HOUR_FEATURES_CSV)

        print("spark_transform progress: writing spark_zone_summary parquet", flush=True)
        zone_summary = zone_hour.groupBy("zone_id").agg(
            F.avg("target_demand_count").alias("avg_hourly_demand"),
            F.stddev("target_demand_count").alias("demand_volatility"),
            F.avg(F.col("is_weekend").cast("double")).alias("weekend_share"),
            F.avg(F.col("is_after_hours").cast("double")).alias("after_hours_share"),
            F.avg("high_demand_flag").alias("high_demand_rate"),
        )
        _safe_remove(config.PROCESSED_DIR / "spark_zone_summary.parquet")
        zone_summary.write.mode("overwrite").parquet(str(config.PROCESSED_DIR / "spark_zone_summary.parquet"))

        print("spark_transform progress: collecting final counts and quality metrics", flush=True)
        fact_rows = fact.count()
        zone_hour_rows = zone_hour.count()
        zone_count = zone_hour.select("zone_id").distinct().count()
        weather_join_coverage = fact.filter(F.col("temperature_2m").isNotNull()).count() / fact_rows if fact_rows else 0
        date_bounds = fact.agg(F.min("event_datetime").alias("min_dt"), F.max("event_datetime").alias("max_dt")).collect()[0]
        ended = datetime.now()
        elapsed = time.time() - start_time
        lines = [
            "# PySpark Processing Report",
            "",
            f"- Spark version: `{spark_version}`",
            f"- Java version: `{java_version}`",
            f"- Run mode full: `{not config.SAMPLE_MODE}`",
            f"- Pandas fallback used: `{fallback_used}`",
            f"- Runtime start: `{started.isoformat(timespec='seconds')}`",
            f"- Runtime end: `{ended.isoformat(timespec='seconds')}`",
            f"- Elapsed seconds: `{elapsed:,.1f}`",
            f"- Input cleaned call rows: `{input_rows:,}`",
            f"- Fact output rows: `{fact_rows:,}`",
            f"- Zone-hour output rows: `{zone_hour_rows:,}`",
            f"- Number of zones/beats: `{zone_count:,}`",
            f"- Date range: `{date_bounds['min_dt']}` to `{date_bounds['max_dt']}`",
            f"- Weather join coverage: `{weather_join_coverage:.2%}`",
            f"- Fact output: `{config.FACT_EVENTS_PARQUET}`",
            f"- Zone-hour output: `{config.ZONE_HOUR_FEATURES_PARQUET}`",
            f"- Zone-hour CSV: `{config.ZONE_HOUR_FEATURES_CSV}`",
        ]
        (config.MEMO_OUTPUT_DIR / "pyspark_processing_report.md").write_text("\n".join(lines), encoding="utf-8")
        (config.MEMO_OUTPUT_DIR / "weather_join_quality.md").write_text(
            "\n".join(
                [
                    "# Weather Join Quality",
                    "",
                    f"- Event rows evaluated: `{fact_rows:,}`",
                    f"- Hourly weather rows: `{weather.count():,}`",
                    f"- Exact hour join coverage: `{weather_join_coverage:.2%}`",
                    "- Join method: Spark hourly timestamp join using `event_datetime` floored to hour.",
                ]
            ),
            encoding="utf-8",
        )
        logger.info("Spark full transform completed with %s fact rows and %s zone-hour rows", fact_rows, zone_hour_rows)
    finally:
        spark.stop()


if __name__ == "__main__":
    run_spark_transform()
