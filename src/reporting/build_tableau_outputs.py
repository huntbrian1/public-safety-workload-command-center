from __future__ import annotations

import shutil

from src import config
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


COPY_MAP = {
    "hex_hourly_demand.csv": "tableau_hourly_demand.csv",
    "hex_zone_summary.csv": "tableau_zone_summary.csv",
    "hex_category_summary.csv": "tableau_category_summary.csv",
    "hex_cluster_profiles.csv": "tableau_cluster_profiles.csv",
    "hex_model_predictions.csv": "tableau_model_predictions.csv",
    "hex_recommendations.csv": "tableau_product_recommendations.csv",
    "hex_executive_kpis.csv": "tableau_executive_kpis.csv",
    "hex_workload_risk_scores.csv": "tableau_workload_risk_scores.csv",
}


def build_tableau_outputs() -> None:
    config.ensure_directories()
    for src_name, dst_name in COPY_MAP.items():
        src = config.HEX_OUTPUT_DIR / src_name
        dst = config.TABLEAU_OUTPUT_DIR / dst_name
        if src.exists():
            shutil.copyfile(src, dst)
            logger.info("Copied %s -> %s", src_name, dst_name)


if __name__ == "__main__":
    build_tableau_outputs()
