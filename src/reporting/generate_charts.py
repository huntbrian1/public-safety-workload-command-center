from __future__ import annotations

import pandas as pd

from src import config
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


def generate_charts() -> None:
    config.ensure_directories()
    try:
        import matplotlib.pyplot as plt
    except Exception as exc:
        (config.MEMO_OUTPUT_DIR / "chart_generation_report.md").write_text(f"Matplotlib unavailable; charts were not generated. Reason: {exc}\n", encoding="utf-8")
        logger.warning("Matplotlib unavailable: %s", exc)
        return

    zone = pd.read_csv(config.HEX_OUTPUT_DIR / "hex_zone_summary.csv")
    cat = pd.read_csv(config.HEX_OUTPUT_DIR / "hex_category_summary.csv")
    hourly = pd.read_csv(config.HEX_OUTPUT_DIR / "hex_hourly_demand.csv")

    plt.figure(figsize=(10, 6))
    top = zone.head(15).sort_values("total_events")
    plt.barh(top["zone_id"], top["total_events"])
    plt.title("Top Zones by Service Demand")
    plt.xlabel("Events")
    plt.tight_layout()
    plt.savefig(config.CHART_OUTPUT_DIR / "top_zones_by_demand.png", dpi=160)
    plt.close()

    plt.figure(figsize=(10, 6))
    ctop = cat.head(15).sort_values("demand_count")
    plt.barh(ctop["normalized_service_category"], ctop["demand_count"])
    plt.title("Top Service Categories")
    plt.xlabel("Events")
    plt.tight_layout()
    plt.savefig(config.CHART_OUTPUT_DIR / "top_service_categories.png", dpi=160)
    plt.close()

    pivot = hourly.pivot_table(index="weekday_name", columns="event_hour", values="demand_count", aggfunc="sum").fillna(0)
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    pivot = pivot.reindex([d for d in order if d in pivot.index])
    plt.figure(figsize=(12, 5))
    plt.imshow(pivot, aspect="auto")
    plt.yticks(range(len(pivot.index)), pivot.index)
    plt.xticks(range(len(pivot.columns)), pivot.columns, rotation=90)
    plt.title("Demand by Weekday and Hour")
    plt.colorbar(label="Events")
    plt.tight_layout()
    plt.savefig(config.CHART_OUTPUT_DIR / "weekday_hour_heatmap.png", dpi=160)
    plt.close()

    (config.MEMO_OUTPUT_DIR / "chart_generation_report.md").write_text("Generated chart PNGs in outputs/charts.\n", encoding="utf-8")
    logger.info("Charts generated")


if __name__ == "__main__":
    generate_charts()
