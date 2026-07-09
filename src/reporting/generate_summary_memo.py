from __future__ import annotations

import pandas as pd

from src import config


def generate_summary_memo() -> None:
    zone = pd.read_csv(config.HEX_OUTPUT_DIR / "hex_zone_summary.csv") if (config.HEX_OUTPUT_DIR / "hex_zone_summary.csv").exists() else pd.DataFrame()
    category = pd.read_csv(config.HEX_OUTPUT_DIR / "hex_category_summary.csv") if (config.HEX_OUTPUT_DIR / "hex_category_summary.csv").exists() else pd.DataFrame()
    model_eval = (config.MEMO_OUTPUT_DIR / "model_evaluation.md").read_text(encoding="utf-8") if (config.MEMO_OUTPUT_DIR / "model_evaluation.md").exists() else "Model evaluation has not been generated yet."
    lines = [
        "# Public Safety Service Demand Intelligence Memo",
        "",
        "## Demand Concentration",
        "",
        f"Highest workload-risk zone: `{zone.iloc[0]['zone_id'] if not zone.empty else 'n/a'}`.",
        "",
        "## Category Drivers",
        "",
        f"Top service category: `{category.iloc[0]['normalized_service_category'] if not category.empty else 'n/a'}`.",
        "",
        "## Model Interpretation",
        "",
        "Forecast outputs estimate aggregate zone-hour workload risk. They should be used for resource-planning visibility, command-center prioritization, and client service analytics.",
        "",
        "## Product/Service Opportunities",
        "",
        "- Demand-spike alerting",
        "- Zone-level workload-risk scoring",
        "- Command-center demand heatmap",
        "- Category mix trend monitoring",
        "- Staffing/resource scenario planner",
        "- Weather-aware demand monitoring",
        "- Recurring demand pattern reporting",
        "",
        "## Model Evaluation Reference",
        "",
        model_eval[:4000],
    ]
    (config.MEMO_OUTPUT_DIR / "summary_memo.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    generate_summary_memo()
