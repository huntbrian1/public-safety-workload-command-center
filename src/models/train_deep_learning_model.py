from __future__ import annotations

import json
import pickle

from src import config
from src.models.train_demand_model import NUMERIC_FEATURES, _metrics, load_model_frames
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


def train_deep_learning_model() -> None:
    config.ensure_directories()
    metadata = {}
    try:
        from sklearn.impute import SimpleImputer
        from sklearn.metrics import classification_report
        from sklearn.neural_network import MLPClassifier
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler

        train, test, metadata = load_model_frames(train_cap=100_000, test_cap=100_000)
        if train["high_demand_flag"].nunique() < 2:
            raise RuntimeError("MLP training sample contains fewer than two target classes.")
        model = Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                (
                    "mlp",
                    MLPClassifier(
                        hidden_layer_sizes=(32, 16),
                        max_iter=220,
                        random_state=config.RANDOM_SEED,
                        early_stopping=True,
                    ),
                ),
            ]
        )
        model.fit(train[NUMERIC_FEATURES], train["high_demand_flag"].astype(int))
        pred = model.predict(test[NUMERIC_FEATURES])
        prob = model.predict_proba(test[NUMERIC_FEATURES])[:, 1]
        metrics = _metrics(test["high_demand_flag"].astype(int), pred, prob)
        with open(config.MODEL_OUTPUT_DIR / "deep_learning_model.pkl", "wb") as f:
            pickle.dump(model, f)
        report = classification_report(test["high_demand_flag"].astype(int), pred, zero_division=0)
        status = "REAL_MLP_COMPARISON_COMPLETED"
        message = "The MLP comparison trained successfully on a capped modeling sample derived from the full zone-hour feature table."
    except Exception as exc:
        metrics = {}
        report = str(exc)
        status = "MLP_COMPARISON_FAILED"
        message = "The MLP comparison did not train successfully in this run. The failure is reported directly rather than treated as success."
        logger.warning("Deep learning comparison failed: %s", exc)

    lines = [
        "# Deep Learning Comparison",
        "",
        message,
        "",
        f"- Status: `{status}`",
        f"- Run mode full: `{not config.SAMPLE_MODE}`",
        f"- Feature rows in full zone-hour table: `{metadata.get('feature_rows_full', 0):,}`",
        f"- Model train rows used: `{metadata.get('train_rows_model', 0):,}`",
        f"- Model test rows used: `{metadata.get('test_rows_model', 0):,}`",
        f"- Loader: `{metadata.get('frame_loader', 'not_available')}`",
        "",
        "## Metrics",
        "",
        "```json",
        json.dumps(metrics, indent=2),
        "```",
        "",
        "## Notes",
        "",
        "```text",
        report,
        "```",
    ]
    (config.MEMO_OUTPUT_DIR / "deep_learning_model_evaluation.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    train_deep_learning_model()
