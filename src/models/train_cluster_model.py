from __future__ import annotations

import os
import pickle
from pathlib import Path

import pandas as pd

from src import config
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


FEATURE_COLS = [
    "avg_hourly_demand",
    "weekend_share",
    "after_hours_share",
    "top_category_share",
    "demand_volatility",
    "weather_sensitivity_proxy",
    "peak_hour_concentration",
    "month_to_month_variability",
    "business_hour_share",
]


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


def _zone_features(zone_hour: pd.DataFrame) -> pd.DataFrame:
    z = zone_hour.copy()
    z["precip_or_rain"] = z[["precipitation", "rain"]].fillna(0).sum(axis=1)
    base = z.groupby("zone_id").agg(
        avg_hourly_demand=("target_demand_count", "mean"),
        weekend_share=("is_weekend", "mean"),
        after_hours_share=("is_after_hours", "mean"),
        top_category_share=("category_mix_top_1_share", "mean"),
        demand_volatility=("target_demand_count", "std"),
        business_hour_share=("is_business_hour", "mean"),
    ).reset_index()
    peak = z.groupby(["zone_id", "hour"])["target_demand_count"].sum().reset_index()
    peak["share"] = peak["target_demand_count"] / peak.groupby("zone_id")["target_demand_count"].transform("sum")
    peak = peak.groupby("zone_id")["share"].max().reset_index(name="peak_hour_concentration")
    monthly = z.groupby(["zone_id", "month"])["target_demand_count"].sum().reset_index()
    monthly_var = monthly.groupby("zone_id")["target_demand_count"].std().reset_index(name="month_to_month_variability")

    sensitivity_rows = []
    for zone, sub in z.groupby("zone_id"):
        if sub["precip_or_rain"].nunique(dropna=True) > 1 and len(sub) > 5:
            corr = sub[["target_demand_count", "precip_or_rain"]].corr().iloc[0, 1]
        else:
            corr = 0
        sensitivity_rows.append({"zone_id": zone, "weather_sensitivity_proxy": 0 if pd.isna(corr) else abs(float(corr))})
    sens = pd.DataFrame(sensitivity_rows)
    out = base.merge(peak, on="zone_id", how="left").merge(monthly_var, on="zone_id", how="left").merge(sens, on="zone_id", how="left")
    out[FEATURE_COLS] = out[FEATURE_COLS].fillna(0)
    return out


def _zone_features_spark() -> tuple[pd.DataFrame, dict]:
    _ensure_local_java()
    from pyspark.sql import SparkSession, Window
    from pyspark.sql import functions as F

    spark = (
        SparkSession.builder.appName("public-safety-zone-cluster-features")
        .config("spark.sql.session.timeZone", "America/Los_Angeles")
        .config("spark.sql.shuffle.partitions", "96")
        .config("spark.driver.memory", "6g")
        .getOrCreate()
    )
    try:
        z = spark.read.parquet(str(config.ZONE_HOUR_FEATURES_PARQUET))
        source_rows = z.count()
        for col in ["precipitation", "rain", "target_demand_count", "category_mix_top_1_share"]:
            if col not in z.columns:
                z = z.withColumn(col, F.lit(0.0))
            z = z.withColumn(col, F.coalesce(F.col(col).cast("double"), F.lit(0.0)))
        for col in ["is_weekend", "is_after_hours", "is_business_hour"]:
            if col not in z.columns:
                z = z.withColumn(col, F.lit(0.0))
            z = z.withColumn(col, F.coalesce(F.col(col).cast("double"), F.lit(0.0)))
        z = z.withColumn("zone_id", F.coalesce(F.col("zone_id").cast("string"), F.lit("UNKNOWN")))
        z = z.withColumn("precip_or_rain", F.col("precipitation") + F.col("rain"))

        base = z.groupBy("zone_id").agg(
            F.avg("target_demand_count").alias("avg_hourly_demand"),
            F.avg("is_weekend").alias("weekend_share"),
            F.avg("is_after_hours").alias("after_hours_share"),
            F.avg("category_mix_top_1_share").alias("top_category_share"),
            F.stddev("target_demand_count").alias("demand_volatility"),
            F.avg("is_business_hour").alias("business_hour_share"),
        )
        peak = z.groupBy("zone_id", "hour").agg(F.sum("target_demand_count").alias("hour_demand"))
        peak_window = Window.partitionBy("zone_id")
        peak = peak.withColumn("share", F.col("hour_demand") / F.sum("hour_demand").over(peak_window))
        peak = peak.groupBy("zone_id").agg(F.max("share").alias("peak_hour_concentration"))
        monthly = z.groupBy("zone_id", "month").agg(F.sum("target_demand_count").alias("month_demand"))
        monthly_var = monthly.groupBy("zone_id").agg(F.stddev("month_demand").alias("month_to_month_variability"))
        sens = z.groupBy("zone_id").agg(
            F.abs(F.coalesce(F.corr("target_demand_count", "precip_or_rain"), F.lit(0.0))).alias("weather_sensitivity_proxy")
        )
        features = base.join(peak, "zone_id", "left").join(monthly_var, "zone_id", "left").join(sens, "zone_id", "left")
        features = features.fillna(0, subset=FEATURE_COLS)
        out = features.toPandas()
        out[FEATURE_COLS] = out[FEATURE_COLS].fillna(0)
        metadata = {
            "frame_loader": "pyspark_parquet",
            "spark_version": spark.version,
            "source_rows": int(source_rows),
            "zone_rows": int(len(out)),
        }
        return out, metadata
    finally:
        spark.stop()


def _name_cluster(row: pd.Series, medians: pd.Series) -> str:
    if row["avg_hourly_demand"] >= medians["avg_hourly_demand"] and row["demand_volatility"] <= medians["demand_volatility"]:
        return "High-volume steady demand zones"
    if row["weekend_share"] >= medians["weekend_share"] and row["peak_hour_concentration"] >= medians["peak_hour_concentration"]:
        return "Weekend/event-driven zones"
    if row["after_hours_share"] >= medians["after_hours_share"]:
        return "Late-night demand zones"
    if row["weather_sensitivity_proxy"] >= medians["weather_sensitivity_proxy"] and row["weather_sensitivity_proxy"] > 0:
        return "Weather-sensitive zones"
    return "Low-volume stable zones"


def train_cluster_model() -> None:
    config.ensure_directories()
    if not config.SAMPLE_MODE and config.ZONE_HOUR_FEATURES_PARQUET.exists():
        features, metadata = _zone_features_spark()
    else:
        zone_hour = pd.read_csv(config.ZONE_HOUR_FEATURES_CSV, parse_dates=["date_hour", "date"])
        features = _zone_features(zone_hour)
        metadata = {"frame_loader": "pandas_csv", "source_rows": int(len(zone_hour)), "zone_rows": int(len(features))}

    try:
        from sklearn.cluster import KMeans
        from sklearn.decomposition import PCA
        from sklearn.preprocessing import StandardScaler

        n_clusters = min(5, max(1, len(features)))
        scaler = StandardScaler()
        x = scaler.fit_transform(features[FEATURE_COLS])
        model = KMeans(n_clusters=n_clusters, random_state=config.RANDOM_SEED, n_init=10)
        features["cluster_id"] = model.fit_predict(x)
        if len(features) >= 2:
            pca = PCA(n_components=min(2, len(FEATURE_COLS), len(features)))
            pcs = pca.fit_transform(x)
            features["pca_1"] = pcs[:, 0]
            features["pca_2"] = pcs[:, 1] if pcs.shape[1] > 1 else 0
        else:
            pca = None
            features["pca_1"] = 0
            features["pca_2"] = 0
        with open(config.MODEL_OUTPUT_DIR / "cluster_model.pkl", "wb") as f:
            pickle.dump({"model": model, "scaler": scaler, "pca": pca, "features": FEATURE_COLS}, f)
        model_status = "KMeans clustering completed."
    except Exception as exc:
        logger.warning("KMeans unavailable; using rule-based cluster ids. Reason: %s", exc)
        features["cluster_id"] = pd.qcut(features["avg_hourly_demand"].rank(method="first"), q=min(5, len(features)), labels=False, duplicates="drop")
        features["pca_1"] = 0
        features["pca_2"] = 0
        model_status = f"KMeans failed; rule-based cluster ids were used. Reason: {exc}"

    medians = features[FEATURE_COLS].median(numeric_only=True)
    cluster_names = features.groupby("cluster_id")[FEATURE_COLS].mean().apply(lambda row: _name_cluster(row, medians), axis=1).to_dict()
    features["cluster_name"] = features["cluster_id"].map(cluster_names)
    profiles = features[["zone_id", "cluster_id", "cluster_name", *FEATURE_COLS, "pca_1", "pca_2"]]
    profiles.to_csv(config.HEX_OUTPUT_DIR / "hex_cluster_profiles.csv", index=False)
    profiles.to_csv(config.TABLEAU_OUTPUT_DIR / "tableau_cluster_profiles.csv", index=False)

    lines = [
        "# Cluster Methodology",
        "",
        model_status,
        "",
        "KMeans segments zones/beats into operational demand profiles using workload volume, weekend and after-hours shares, category concentration, volatility, weather sensitivity proxy, peak-hour concentration, and monthly variability.",
        "",
        "Cluster names are business-facing labels derived from each cluster's dominant signal. They are intended for planning conversations and product/service analytics, not individual-level decisioning.",
        "",
        f"- Run mode full: `{not config.SAMPLE_MODE}`",
        f"- Feature loader: `{metadata.get('frame_loader')}`",
        f"- Source zone-hour rows: `{metadata.get('source_rows', 0):,}`",
        f"- Zones clustered: `{len(profiles):,}`",
    ]
    if "spark_version" in metadata:
        lines.append(f"- Spark version: `{metadata['spark_version']}`")
    (config.MEMO_OUTPUT_DIR / "cluster_methodology.md").write_text("\n".join(lines), encoding="utf-8")
    logger.info("Cluster profiles written")


if __name__ == "__main__":
    train_cluster_model()
