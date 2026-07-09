from __future__ import annotations

import json
import os
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

from src import config
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


NUMERIC_FEATURES = [
    "hour",
    "weekday",
    "month",
    "quarter",
    "is_weekend",
    "is_holiday",
    "is_business_hour",
    "is_after_hours",
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "rain",
    "snowfall",
    "weather_code",
    "wind_speed_10m",
    "lag_1_hour_demand",
    "lag_24_hour_demand",
    "rolling_7_day_avg",
    "prior_week_same_hour_demand",
    "category_mix_top_1_share",
    "category_mix_top_3_share",
]

MAX_RF_TRAIN_ROWS = int(os.getenv("MAX_RF_TRAIN_ROWS", "500000"))
MAX_RF_TEST_ROWS = int(os.getenv("MAX_RF_TEST_ROWS", "200000"))


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


def _metrics(y_true, y_pred, y_prob) -> dict:
    from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score

    out = {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "confusion_matrix": confusion_matrix(y_true, y_pred).tolist(),
    }
    out["roc_auc"] = float(roc_auc_score(y_true, y_prob)) if len(set(y_true)) > 1 else None
    return out


def _coerce_model_frame(data: pd.DataFrame) -> pd.DataFrame:
    data = data.copy()
    for col in NUMERIC_FEATURES:
        if col not in data:
            data[col] = 0
        data[col] = pd.to_numeric(data[col], errors="coerce").fillna(0)
    data["zone_id"] = data["zone_id"].astype(str).fillna("UNKNOWN")
    data["high_demand_flag"] = pd.to_numeric(data["high_demand_flag"], errors="coerce").fillna(0).astype(int)
    data["target_demand_count"] = pd.to_numeric(data["target_demand_count"], errors="coerce").fillna(0)
    data["date_hour"] = pd.to_datetime(data["date_hour"], errors="coerce")
    if "date" in data:
        data["date"] = pd.to_datetime(data["date"], errors="coerce")
    return data.sort_values("date_hour").reset_index(drop=True)


def _sample_spark_frame(df, target_rows: int, total_rows: int, seed: int):
    if total_rows <= target_rows:
        return df
    fraction = min(1.0, target_rows / max(total_rows, 1) * 1.15)
    return df.sample(withReplacement=False, fraction=fraction, seed=seed).limit(target_rows)


def load_model_frames(train_cap: int = MAX_RF_TRAIN_ROWS, test_cap: int = MAX_RF_TEST_ROWS) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Return practical modeling frames derived from the full zone-hour feature table."""
    metadata: dict = {
        "sample_mode": config.SAMPLE_MODE,
        "source": str(config.ZONE_HOUR_FEATURES_PARQUET if config.ZONE_HOUR_FEATURES_PARQUET.exists() else config.ZONE_HOUR_FEATURES_CSV),
        "train_cap": train_cap,
        "test_cap": test_cap,
    }

    if not config.SAMPLE_MODE and config.ZONE_HOUR_FEATURES_PARQUET.exists():
        _ensure_local_java()
        from pyspark.sql import SparkSession
        from pyspark.sql import functions as F

        spark = (
            SparkSession.builder.appName("public-safety-demand-model-frame")
            .config("spark.sql.session.timeZone", "America/Los_Angeles")
            .config("spark.sql.shuffle.partitions", "96")
            .config("spark.driver.memory", "6g")
            .getOrCreate()
        )
        try:
            z = spark.read.parquet(str(config.ZONE_HOUR_FEATURES_PARQUET))
            for col in NUMERIC_FEATURES:
                if col not in z.columns:
                    z = z.withColumn(col, F.lit(0.0))
                z = z.withColumn(col, F.coalesce(F.col(col).cast("double"), F.lit(0.0)))
            z = (
                z.withColumn("zone_id", F.coalesce(F.col("zone_id").cast("string"), F.lit("UNKNOWN")))
                .withColumn("high_demand_flag", F.coalesce(F.col("high_demand_flag").cast("int"), F.lit(0)))
                .withColumn("target_demand_count", F.coalesce(F.col("target_demand_count").cast("double"), F.lit(0.0)))
                .withColumn("date_hour", F.to_timestamp("date_hour"))
                .withColumn("date", F.to_date("date"))
                .withColumn("date_hour_epoch", F.unix_timestamp("date_hour"))
            )
            selected = ["zone_id", "date", "date_hour", "target_demand_count", "high_demand_flag", *NUMERIC_FEATURES]
            feature_rows = z.count()
            cutoff = z.approxQuantile("date_hour_epoch", [0.80], 0.001)[0]
            train_full = z.filter(F.col("date_hour_epoch") <= F.lit(cutoff))
            test_full = z.filter(F.col("date_hour_epoch") > F.lit(cutoff))
            train_rows_full = train_full.count()
            test_rows_full = test_full.count()
            if test_rows_full == 0:
                test_full = train_full
                test_rows_full = train_rows_full
            threshold = train_full.approxQuantile("target_demand_count", [0.75], 0.001)[0]

            train_sample = _sample_spark_frame(train_full, train_cap, train_rows_full, config.RANDOM_SEED)
            test_sample = _sample_spark_frame(test_full, test_cap, test_rows_full, config.RANDOM_SEED + 1)
            train = _coerce_model_frame(train_sample.select(*selected).toPandas())
            test = _coerce_model_frame(test_sample.select(*selected).toPandas())
            metadata.update(
                {
                    "frame_loader": "pyspark_parquet",
                    "spark_version": spark.version,
                    "feature_rows_full": int(feature_rows),
                    "train_rows_full": int(train_rows_full),
                    "test_rows_full": int(test_rows_full),
                    "train_rows_model": int(len(train)),
                    "test_rows_model": int(len(test)),
                    "temporal_split_epoch_80pct": float(cutoff),
                    "high_demand_threshold_full_train": float(threshold),
                    "prediction_scope": "model evaluation and prediction outputs use capped samples from the full zone-hour feature table",
                }
            )
            return train, test, metadata
        finally:
            spark.stop()

    data = _coerce_model_frame(pd.read_csv(config.ZONE_HOUR_FEATURES_CSV, parse_dates=["date_hour", "date"]))
    split_idx = max(1, int(len(data) * 0.8))
    train = data.iloc[:split_idx].copy()
    test = data.iloc[split_idx:].copy()
    if test.empty:
        test = train.copy()
    metadata.update(
        {
            "frame_loader": "pandas_csv",
            "feature_rows_full": int(len(data)),
            "train_rows_full": int(len(train)),
            "test_rows_full": int(len(test)),
            "train_rows_model": int(len(train)),
            "test_rows_model": int(len(test)),
            "high_demand_threshold_full_train": float(train["target_demand_count"].quantile(0.75)),
            "prediction_scope": "sample-mode CSV frame",
        }
    )
    return train, test, metadata


def train_demand_model() -> None:
    config.ensure_directories()
    train, test, metadata = load_model_frames()
    y_train = train["high_demand_flag"].astype(int)
    y_test = test["high_demand_flag"].astype(int)

    threshold = metadata.get("high_demand_threshold_full_train")
    if threshold is None or pd.isna(threshold):
        threshold = train["target_demand_count"].quantile(0.75)
    baseline_pred = (test["prior_week_same_hour_demand"].fillna(0) >= threshold).astype(int)
    baseline_prob = np.clip(test["prior_week_same_hour_demand"].fillna(0) / max(float(threshold), 1.0), 0, 1)

    try:
        from sklearn.compose import ColumnTransformer
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.impute import SimpleImputer
        from sklearn.metrics import classification_report
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import OneHotEncoder, StandardScaler

        preprocessor = ColumnTransformer(
            transformers=[
                ("num", Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())]), NUMERIC_FEATURES),
                ("zone", OneHotEncoder(handle_unknown="ignore"), ["zone_id"]),
            ]
        )
        model = Pipeline(
            steps=[
                ("preprocess", preprocessor),
                (
                    "model",
                    RandomForestClassifier(
                        n_estimators=100,
                        max_depth=18,
                        min_samples_leaf=3,
                        random_state=config.RANDOM_SEED,
                        n_jobs=1,
                    ),
                ),
            ]
        )
        model.fit(train[NUMERIC_FEATURES + ["zone_id"]], y_train)
        ml_pred = model.predict(test[NUMERIC_FEATURES + ["zone_id"]])
        ml_prob = model.predict_proba(test[NUMERIC_FEATURES + ["zone_id"]])[:, 1]
        with open(config.MODEL_OUTPUT_DIR / "demand_model.pkl", "wb") as f:
            pickle.dump(model, f)
        report_text = classification_report(y_test, ml_pred, zero_division=0)
        model_status = "Random Forest trained successfully on a capped modeling sample derived from the full zone-hour table."
    except Exception as exc:
        logger.warning("Traditional ML model failed; using baseline-only output. Reason: %s", exc)
        ml_pred = baseline_pred.to_numpy()
        ml_prob = baseline_prob.to_numpy()
        report_text = f"Traditional ML model unavailable: {exc}"
        model_status = f"Random Forest failed and baseline output was used. Reason: {exc}"

    baseline_metrics = _metrics(y_test, baseline_pred, baseline_prob)
    ml_metrics = _metrics(y_test, ml_pred, ml_prob)

    pred_out = test[["zone_id", "date_hour", "target_demand_count", "high_demand_flag"]].copy()
    pred_out = pred_out.rename(columns={"high_demand_flag": "actual_high_demand"})
    pred_out["baseline_prediction"] = baseline_pred.to_numpy()
    pred_out["ml_prediction"] = ml_pred
    pred_out["predicted_high_demand_probability"] = ml_prob
    pred_out["workload_risk_score"] = (pred_out["predicted_high_demand_probability"] * 100).round(1)
    pred_out.to_csv(config.HEX_OUTPUT_DIR / "hex_model_predictions.csv", index=False)
    pred_out.to_csv(config.TABLEAU_OUTPUT_DIR / "tableau_model_predictions.csv", index=False)

    evaluation = {"metadata": metadata, "baseline": baseline_metrics, "traditional_ml": ml_metrics}
    (config.MODEL_OUTPUT_DIR / "model_evaluation.json").write_text(json.dumps(evaluation, indent=2), encoding="utf-8")
    lines = [
        "# Model Evaluation",
        "",
        model_status,
        "",
        f"- Run mode full: `{not config.SAMPLE_MODE}`",
        f"- Feature rows in full zone-hour table: `{metadata.get('feature_rows_full', 0):,}`",
        f"- Full train rows before cap: `{metadata.get('train_rows_full', 0):,}`",
        f"- Full test rows before cap: `{metadata.get('test_rows_full', 0):,}`",
        f"- Model train rows used: `{metadata.get('train_rows_model', 0):,}`",
        f"- Model test/prediction rows used: `{metadata.get('test_rows_model', 0):,}`",
        f"- Loader: `{metadata.get('frame_loader')}`",
        "",
        "The full zone-hour feature table is the modeling grain. The Random Forest uses capped train/test samples for local runtime practicality, with the split and caps documented here.",
        "",
        "## Baseline",
        "",
        "```json",
        json.dumps(baseline_metrics, indent=2),
        "```",
        "",
        "## Traditional ML",
        "",
        "```json",
        json.dumps(ml_metrics, indent=2),
        "```",
        "",
        "## Classification Report",
        "",
        "```text",
        report_text,
        "```",
    ]
    (config.MEMO_OUTPUT_DIR / "model_evaluation.md").write_text("\n".join(lines), encoding="utf-8")
    (config.MEMO_OUTPUT_DIR / "model_methodology.md").write_text(
        "\n".join(
            [
                "# Model Methodology",
                "",
                "Baseline predictions use prior-week same-hour demand and a historical high-demand threshold computed from the full training window. The traditional ML comparison uses a Random Forest classifier over calendar, weather, lagged demand, category mix, and zone features.",
                "",
                f"- Modeling grain: `zone-hour`",
                f"- Full feature rows available: `{metadata.get('feature_rows_full', 0):,}`",
                f"- Train cap used for Random Forest: `{metadata.get('train_cap'):,}`",
                f"- Test/prediction cap used for Random Forest: `{metadata.get('test_cap'):,}`",
                "",
                "The cap keeps local runtime practical while ensuring samples are derived from the completed full-scale feature build. Performance should be interpreted as a planning aid for workload visibility and command-center prioritization.",
            ]
        ),
        encoding="utf-8",
    )
    logger.info("Demand model predictions written")


if __name__ == "__main__":
    train_demand_model()
