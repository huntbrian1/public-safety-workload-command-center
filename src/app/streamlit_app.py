from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[2]
HEX_DIR = PROJECT_ROOT / "outputs" / "hex"
MEMO_DIR = PROJECT_ROOT / "outputs" / "memo"


st.set_page_config(page_title="Public Safety Service Demand Intelligence", layout="wide")
st.title("Public Safety Service Demand Intelligence Platform")
st.caption("Operational workload visibility, service-event metadata analysis, and product/service planning outputs")


def read_csv(name: str) -> pd.DataFrame:
    path = HEX_DIR / name
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


page = st.sidebar.radio(
    "View",
    [
        "Overview",
        "Data Quality",
        "Demand Trends",
        "Zone Profiles",
        "Cluster Analysis",
        "Model Performance",
        "Recommendations",
        "Methodology",
    ],
)

kpis = read_csv("hex_executive_kpis.csv")
hourly = read_csv("hex_hourly_demand.csv")
zones = read_csv("hex_zone_summary.csv")
category = read_csv("hex_category_summary.csv")
clusters = read_csv("hex_cluster_profiles.csv")
preds = read_csv("hex_model_predictions.csv")
recs = read_csv("hex_recommendations.csv")
quality = read_csv("hex_data_quality_summary.csv")

if page == "Overview":
    if not kpis.empty:
        cols = st.columns(min(4, len(kpis)))
        for idx, row in kpis.head(4).iterrows():
            cols[idx % len(cols)].metric(str(row["metric"]).replace("_", " ").title(), row["value"])
    st.subheader("Executive Workload-Risk View")
    st.dataframe(zones.head(25), use_container_width=True)
elif page == "Data Quality":
    st.subheader("Data Integration & Quality")
    st.dataframe(quality, use_container_width=True)
elif page == "Demand Trends":
    st.subheader("Demand by Hour and Weekday")
    if not hourly.empty:
        pivot = hourly.pivot_table(index="weekday_name", columns="event_hour", values="demand_count", aggfunc="sum").fillna(0)
        st.dataframe(pivot, use_container_width=True)
    st.subheader("Service Category Mix")
    st.dataframe(category.head(30), use_container_width=True)
elif page == "Zone Profiles":
    st.subheader("Zone/Beat Workload Profiles")
    st.dataframe(zones, use_container_width=True)
elif page == "Cluster Analysis":
    st.subheader("Operational Demand Clusters")
    st.dataframe(clusters, use_container_width=True)
elif page == "Model Performance":
    st.subheader("High-Demand Forecast Output")
    st.dataframe(preds.head(1000), use_container_width=True)
    eval_path = MEMO_DIR / "model_evaluation.md"
    if eval_path.exists():
        st.markdown(eval_path.read_text(encoding="utf-8"))
elif page == "Recommendations":
    st.subheader("Product/Service Recommendations")
    st.dataframe(recs, use_container_width=True)
elif page == "Methodology":
    for name in ["executive_summary.md", "model_methodology.md", "cluster_methodology.md", "limitations.md"]:
        path = MEMO_DIR / name
        if path.exists():
            st.markdown(path.read_text(encoding="utf-8"))
