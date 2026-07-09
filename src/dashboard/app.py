from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

try:
    from pyproj import Transformer
except Exception:
    Transformer = None

PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_DIR = PROJECT_ROOT / "data" / "app"
GEOJSON_PATH = APP_DIR / "seattle_police_beats.geojson"
FALLBACK_GEOJSON_PATH = PROJECT_ROOT / "data" / "external" / "seattle_police_beats.geojson"

BRAND_BLUE = "#2563eb"
BRAND_TEAL = "#0f766e"

st.set_page_config(page_title="Public Safety Workload Command Center", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""
<style>
#MainMenu, footer, header {visibility:hidden;}
.block-container {max-width:1520px; padding-top:1rem; padding-bottom:2.5rem;}
h1,h2,h3 {letter-spacing:0 !important; color:#132033;}
.hero {background:linear-gradient(135deg,#08111f 0%,#0d233b 58%,#11425e 100%); border-radius:8px; padding:30px 34px 28px; color:#fff; box-shadow:0 20px 45px rgba(15,23,42,.20); margin-bottom:18px;}
.hero-title {color:#fff; font-size:clamp(2rem,4vw,3.1rem); line-height:1.03; font-weight:760; margin:0 0 12px;}
.hero-subtitle {color:#d7e2f1; font-size:1.05rem; line-height:1.45; max-width:1040px; margin:0 0 20px;}
.badge-row {display:flex; flex-wrap:wrap; gap:8px;}
.proof-badge {display:inline-flex; background:rgba(255,255,255,.10); border:1px solid rgba(255,255,255,.22); color:#eff6ff; padding:7px 10px; border-radius:999px; font-size:.80rem; white-space:nowrap;}
.kpi-grid {display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; margin:14px 0 18px;}
.kpi-card {background:#fff; border:1px solid #dde5ef; border-radius:8px; padding:16px; box-shadow:0 12px 28px rgba(15,23,42,.06); min-height:106px;}
.kpi-label {color:#64748b; font-size:.75rem; line-height:1.2; text-transform:uppercase; font-weight:700; letter-spacing:.04em; margin-bottom:9px;}
.kpi-value {color:#132033; font-size:clamp(1.35rem,2vw,1.9rem); line-height:1.08; font-weight:760; white-space:normal;}
.kpi-help {color:#64748b; font-size:.78rem; margin-top:7px; line-height:1.25;}
.section-title {font-size:1.24rem; font-weight:760; color:#132033; margin:0 0 2px;}
.section-subtitle {font-size:.89rem; color:#64748b; margin:0 0 12px; line-height:1.35;}
.insight-card {background:#fff; border:1px solid #dde5ef; border-radius:8px; padding:16px; box-shadow:0 10px 24px rgba(15,23,42,.05); margin-bottom:12px;}
.insight-label {font-size:.76rem; color:#64748b; font-weight:720; text-transform:uppercase; letter-spacing:.04em; margin-bottom:6px;}
.insight-value {font-size:1.45rem; color:#132033; font-weight:760; margin-bottom:4px;}
.insight-text {font-size:.90rem; color:#475569; line-height:1.42;}
.qa-card {background:#0f1f33; color:#e7eef8; border-radius:8px; padding:18px; border:1px solid rgba(255,255,255,.10); box-shadow:0 10px 24px rgba(15,23,42,.12);}
.qa-card b {color:#fff;} .qa-card .muted {color:#b8c5d6; font-size:.86rem; line-height:1.45;}
.map-key {border:1px solid #dde5ef; border-radius:8px; padding:12px 14px; margin:-4px 0 10px; background:#fff;}
.map-gradient {height:14px; flex:1; min-width:220px; border-radius:999px; border:1px solid #cbd5e1; background:linear-gradient(90deg, rgba(38,185,148,.34), rgba(94,145,148,.64), rgba(198,105,148,.88));}
.stMultiSelect [data-baseweb="tag"] {background-color:#e8eef6 !important; color:#132033 !important; border:1px solid #cbd5e1 !important;}
div[data-testid="stExpander"] {border:1px solid #dde5ef; border-radius:8px; background:#fff;}
div[data-testid="stVerticalBlockBorderWrapper"] {border-radius:8px; border-color:#dde5ef; box-shadow:0 10px 24px rgba(15,23,42,.05);}
@media (max-width:1050px) {.kpi-grid {grid-template-columns:repeat(2,minmax(0,1fr));}}
@media (max-width:650px) {.kpi-grid {grid-template-columns:1fr;} .hero {padding:24px 20px;}}
</style>
""", unsafe_allow_html=True)

@st.cache_data(show_spinner=False)
def load_csv(name: str) -> pd.DataFrame:
    path = APP_DIR / name
    return pd.read_csv(path) if path.exists() else pd.DataFrame()

@st.cache_data(show_spinner=False)
def load_json(name: str) -> dict[str, Any]:
    path = APP_DIR / name
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}

@st.cache_data(show_spinner=False)
def load_geojson() -> dict[str, Any]:
    path = GEOJSON_PATH if GEOJSON_PATH.exists() else FALLBACK_GEOJSON_PATH
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}

def compact_int(value: Any) -> str:
    if value is None or pd.isna(value): return "Unavailable"
    value = float(value)
    if abs(value) >= 1_000_000: return f"{value / 1_000_000:.2f}M"
    if abs(value) >= 1_000: return f"{value / 1_000:.1f}K"
    return f"{int(value):,}"

def fmt_int(value: Any) -> str:
    return "Unavailable" if value is None or pd.isna(value) else f"{int(float(value)):,}"

def fmt_pct(value: Any, digits: int = 2) -> str:
    return "Unavailable" if value is None or pd.isna(value) else f"{float(value):.{digits}%}"

def period_filter(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    if df.empty or "period" not in df.columns: return df
    return df[(df["period"].astype(str) >= start) & (df["period"].astype(str) <= end)].copy()

def apply_period_type(df: pd.DataFrame, period_type: str) -> pd.DataFrame:
    if df.empty or "is_weekend" not in df.columns or period_type == "All": return df
    mask = df["is_weekend"] if df["is_weekend"].dtype == bool else df["is_weekend"].astype(str).str.lower().isin({"true","1","yes"})
    return df[mask == (period_type == "Weekend")]

def section_title(title: str, subtitle: str | None = None) -> None:
    sub = f'<div class="section-subtitle">{subtitle}</div>' if subtitle else ""
    st.markdown(f'<div class="section-title">{title}</div>{sub}', unsafe_allow_html=True)

def kpi_grid(items: list[tuple[str, str, str]]) -> None:
    cards = [f'<div class="kpi-card"><div class="kpi-label">{a}</div><div class="kpi-value">{b}</div><div class="kpi-help">{c}</div></div>' for a,b,c in items]
    st.markdown(f'<div class="kpi-grid">{"".join(cards)}</div>', unsafe_allow_html=True)

def hero(kpis: dict[str, Any]) -> None:
    st.markdown(f"""
    <div class="hero"><div class="hero-title">Public Safety Workload Command Center</div>
    <div class="hero-subtitle">PySpark-powered service-demand intelligence for workload timing, zone-hour planning, geography, service categories, and weather-context reporting.</div>
    <div class="badge-row"><span class="proof-badge">Full PySpark run</span><span class="proof-badge">{compact_int(kpis.get('cleaned_input_events'))} cleaned events</span><span class="proof-badge">{compact_int(kpis.get('zone_hour_records'))} zone-hour records</span><span class="proof-badge">{fmt_int(kpis.get('active_zones_beats'))} zones/beats</span><span class="proof-badge">pandas fallback disabled</span></div></div>
    """, unsafe_allow_html=True)

def _first_coordinate_pair(coords: Any) -> list[float] | None:
    if isinstance(coords, (list, tuple)) and len(coords) >= 2 and all(isinstance(v, (int, float)) for v in coords[:2]):
        return [float(coords[0]), float(coords[1])]
    if isinstance(coords, (list, tuple)):
        for item in coords:
            pair = _first_coordinate_pair(item)
            if pair is not None: return pair
    return None

def _transform_coordinates(coords: Any, transformer: Any) -> Any:
    if isinstance(coords, (list, tuple)) and len(coords) >= 2 and all(isinstance(v, (int, float)) for v in coords[:2]):
        lon, lat = transformer.transform(float(coords[0]), float(coords[1]))
        return [lon, lat, *list(coords[2:])]
    if isinstance(coords, list): return [_transform_coordinates(item, transformer) for item in coords]
    if isinstance(coords, tuple): return tuple(_transform_coordinates(item, transformer) for item in coords)
    return coords

def reproject_geojson_to_wgs84(geojson: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    pair = _first_coordinate_pair(geojson.get("features", [{}])[0].get("geometry", {}).get("coordinates", [])) if geojson else None
    if pair is None or (abs(pair[0]) <= 180 and abs(pair[1]) <= 90): return geojson, False
    if Transformer is None: return geojson, False
    transformer = Transformer.from_crs("EPSG:2926", "EPSG:4326", always_xy=True)
    transformed = json.loads(json.dumps(geojson))
    for feature in transformed.get("features", []):
        geometry = feature.get("geometry") or {}
        if "coordinates" in geometry: geometry["coordinates"] = _transform_coordinates(geometry["coordinates"], transformer)
    return transformed, True

def _geometry_rings(geometry: dict[str, Any]) -> list[list[list[float]]]:
    coords = geometry.get("coordinates", [])
    if geometry.get("type") == "Polygon": return [coords[0]] if coords else []
    if geometry.get("type") == "MultiPolygon": return [poly[0] for poly in coords if poly]
    return []

def _rgba_from_intensity(intensity: float, alpha: float = 0.72) -> str:
    intensity = max(0.0, min(1.0, intensity))
    return f"rgba({int(38 + 160 * intensity)},{int(185 - 80 * intensity)},148,{alpha:.2f})"

def enrich_geojson(geojson: dict[str, Any], zone_summary: pd.DataFrame) -> tuple[dict[str, Any], int]:
    if not geojson or zone_summary.empty: return geojson, 0
    summary = zone_summary.copy()
    summary["zone_id"] = summary["zone_id"].astype(str).str.upper().str.strip()
    summary = summary.sort_values("total_service_demand", ascending=False).reset_index(drop=True)
    summary["rank"] = summary.index + 1
    summary_map = summary.set_index("zone_id").to_dict(orient="index")
    max_demand = max(float(summary["total_service_demand"].max()), 1.0)
    enriched = json.loads(json.dumps(geojson))
    matched = 0
    for feature in enriched.get("features", []):
        props = feature.setdefault("properties", {})
        beat = str(props.get("beat", "")).upper().strip()
        row = summary_map.get(beat)
        if row:
            matched += 1
            demand = float(row.get("total_service_demand", 0))
            props.update(total_service_demand=demand, avg_calls_per_zone_hour=float(row.get("avg_calls_per_zone_hour", 0)), peak_hour=int(row.get("peak_hour", -1)) if pd.notna(row.get("peak_hour")) else None, weekend_share=float(row.get("weekend_share", 0)), rank=int(row.get("rank", 0)), fill_color=_rgba_from_intensity(demand / max_demand))
        else:
            props.update(total_service_demand=0, avg_calls_per_zone_hour=0, peak_hour=None, weekend_share=0, rank=None, fill_color="rgba(216,226,235,0.34)")
    return enriched, matched

def map_legend(enriched: dict[str, Any]) -> None:
    demands = [float(f.get("properties", {}).get("total_service_demand", 0) or 0) for f in enriched.get("features", [])]
    demands = [d for d in demands if d > 0]
    low = compact_int(min(demands)) if demands else "0"
    high = compact_int(max(demands)) if demands else "0"
    st.markdown(f"""
    <div class="map-key"><div style="font-size:.78rem;color:#64748b;font-weight:760;text-transform:uppercase;letter-spacing:.04em;margin-bottom:8px;">Map key - service demand</div>
    <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;"><span style="font-size:.82rem;color:#475569;min-width:74px;">Lower<br><b>{low}</b></span><div class="map-gradient"></div><span style="font-size:.82rem;color:#475569;min-width:74px;text-align:right;">Higher<br><b>{high}</b></span><span style="display:inline-flex;align-items:center;gap:7px;font-size:.82rem;color:#475569;margin-left:8px;"><span style="width:18px;height:12px;border-radius:3px;border:1px solid #cbd5e1;background:rgba(216,226,235,.55);display:inline-block;"></span>Unmatched / no mapped demand</span></div></div>
    """, unsafe_allow_html=True)

def static_beat_map(enriched: dict[str, Any], matched: int, projected: bool) -> go.Figure:
    fig = go.Figure()
    for feature in enriched.get("features", []):
        props = feature.get("properties", {})
        beat = str(props.get("beat", "Unknown")); demand = float(props.get("total_service_demand", 0) or 0)
        avg = float(props.get("avg_calls_per_zone_hour", 0) or 0); peak = props.get("peak_hour"); rank = props.get("rank")
        for ring in _geometry_rings(feature.get("geometry") or {}):
            if not ring: continue
            fig.add_trace(go.Scatter(x=[p[0] for p in ring], y=[p[1] for p in ring], mode="lines", fill="toself", line=dict(color="rgba(36,50,68,0.58)", width=0.75), fillcolor=props.get("fill_color", "rgba(216,226,235,0.34)"), name=f"Beat {beat}", hovertemplate=f"Beat {beat}<br>Total service demand {demand:,.0f}<br>Rank {rank}<br>Peak hour {peak}:00<br>Avg calls / zone-hour {avg:.2f}<extra></extra>", showlegend=False))
    subtitle = "Seattle beat polygons reprojected to WGS84" if projected else "Seattle beat polygons"
    fig.update_layout(height=560, margin=dict(l=0,r=0,t=26,b=0), paper_bgcolor="white", plot_bgcolor="white", title=dict(text=f"{matched} mapped beat polygons - {subtitle}", font=dict(size=13,color="#64748b"), x=0.01), xaxis=dict(visible=False, scaleanchor="y", scaleratio=1), yaxis=dict(visible=False))
    return fig

def render_map(zone_summary: pd.DataFrame, analytic_zone_count: int) -> None:
    enriched, matched = enrich_geojson(load_geojson(), zone_summary)
    enriched, projected = reproject_geojson_to_wgs84(enriched)
    section_title("Mapped Beat Workload Coverage", f"55 mapped Seattle beat polygons; analytic workload summaries cover {analytic_zone_count} zones/beats.")
    if not enriched:
        st.info("Beat GeoJSON was not found; showing the zone table instead."); st.dataframe(zone_summary.head(50), use_container_width=True, hide_index=True); return
    if Transformer is None and not projected:
        st.warning("Map projection support is unavailable. Install `pyproj` to render projected Seattle beat polygons."); st.dataframe(zone_summary.head(50), use_container_width=True, hide_index=True); return
    map_legend(enriched)
    st.plotly_chart(static_beat_map(enriched, matched, projected), use_container_width=True)
    st.caption("GeoJSON coverage includes 55 matched beat polygons. The complete analytic planning layer contains 156 zones/beats.")

def aggregate_zone_period(zone_period: pd.DataFrame, heatmap: pd.DataFrame, period_type: str = "All") -> pd.DataFrame:
    if period_type != "All" and not heatmap.empty:
        filtered = apply_period_type(heatmap.copy(), period_type)
        if filtered.empty:
            return pd.DataFrame()
        out = filtered.groupby("zone_id", as_index=False).agg(
            total_service_demand=("demand_count", "sum"),
            zone_hour_records=("zone_hour_records", "sum"),
        )
        out["weekend_demand"] = out["total_service_demand"] if period_type == "Weekend" else 0
        out["after_hours_demand"] = 0
        out["high_demand_hours"] = 0
        out["peak_hour_demand"] = 0
        out["avg_calls_per_zone_hour"] = out["total_service_demand"] / out["zone_hour_records"].replace(0, pd.NA)
        out["weekend_share"] = 1.0 if period_type == "Weekend" else 0.0
        out["after_hours_share"] = 0.0
        out["high_demand_hour_rate"] = 0.0
        peak = filtered.groupby(["zone_id", "hour"], as_index=False)["demand_count"].sum()
        if not peak.empty:
            peak = peak.sort_values(["zone_id", "demand_count", "hour"], ascending=[True, False, True]).drop_duplicates("zone_id")
            out = out.merge(peak[["zone_id", "hour"]].rename(columns={"hour": "peak_hour"}), on="zone_id", how="left")
        return out.sort_values("total_service_demand", ascending=False)

    if zone_period.empty:
        return pd.DataFrame()
    sum_cols = ["total_service_demand", "zone_hour_records", "weekend_demand", "after_hours_demand", "high_demand_hours", "peak_hour_demand"]
    out = zone_period.groupby("zone_id", as_index=False)[sum_cols].sum()
    out["avg_calls_per_zone_hour"] = out["total_service_demand"] / out["zone_hour_records"].replace(0, pd.NA)
    out["weekend_share"] = out["weekend_demand"] / out["total_service_demand"].replace(0, pd.NA)
    out["after_hours_share"] = out["after_hours_demand"] / out["total_service_demand"].replace(0, pd.NA)
    out["high_demand_hour_rate"] = out["high_demand_hours"] / out["zone_hour_records"].replace(0, pd.NA)
    peak = heatmap.groupby(["zone_id", "hour"], as_index=False)["demand_count"].sum() if not heatmap.empty else pd.DataFrame()
    if not peak.empty:
        peak = peak.sort_values(["zone_id", "demand_count", "hour"], ascending=[True, False, True]).drop_duplicates("zone_id")
        out = out.merge(peak[["zone_id", "hour"]].rename(columns={"hour": "peak_hour"}), on="zone_id", how="left")
    return out.sort_values("total_service_demand", ascending=False)

def top_zone_chart(zone_summary: pd.DataFrame, n: int = 10) -> go.Figure:
    data = zone_summary.sort_values("total_service_demand", ascending=False).head(n).sort_values("total_service_demand")
    fig = go.Figure(go.Bar(x=data["total_service_demand"], y=data["zone_id"], orientation="h", marker=dict(color="#1f6f78"), text=[compact_int(v) for v in data["total_service_demand"]], textposition="outside", cliponaxis=False, hovertemplate="Zone %{y}<br>Total service demand %{x:,.0f}<extra></extra>"))
    fig.update_layout(height=365, margin=dict(l=4,r=62,t=8,b=4), xaxis=dict(title="Total service demand"), yaxis=dict(title=""), paper_bgcolor="white", plot_bgcolor="white")
    return fig

def heatmap_chart(heatmap: pd.DataFrame, zone_summary: pd.DataFrame, period_type: str, portfolio: bool) -> go.Figure:
    heat = apply_period_type(heatmap.copy(), period_type)
    top_zones = zone_summary.sort_values("total_service_demand", ascending=False).head(20)["zone_id"].tolist()
    heat = heat[heat["zone_id"].isin(top_zones)]
    pivot = heat.pivot_table(index="zone_id", columns="hour", values="demand_count", aggfunc="sum", fill_value=0).reindex(top_zones)
    fig = go.Figure(data=go.Heatmap(z=pivot.values, x=[str(int(c)) for c in pivot.columns], y=pivot.index, colorscale="Tealrose", colorbar=dict(title=dict(text="Service<br>demand", side="right"), thickness=14, len=0.88), hovertemplate="Zone %{y}<br>Hour %{x}:00<br>Service demand %{z:,.0f}<extra></extra>"))
    fig.update_layout(height=650 if portfolio else 720, margin=dict(l=8,r=20,t=12,b=8), xaxis=dict(title="Hour of day", tickmode="linear", dtick=1), yaxis=dict(title="Zone / beat", autorange="reversed"), paper_bgcolor="white", plot_bgcolor="white", font=dict(size=12))
    return fig

def hourly_chart(hourly: pd.DataFrame, period_type: str) -> tuple[go.Figure, dict[str, Any]]:
    filtered = apply_period_type(hourly, period_type)
    plot = filtered.groupby(["hour","is_weekend"], as_index=False)["demand_count"].sum().sort_values("hour")
    plot["period_type"] = plot["is_weekend"].map({True:"Weekend", False:"Weekday"})
    fig = go.Figure(); peak_info = {"hour": None, "context": "Unavailable", "demand": None}
    for name, group in plot.groupby("period_type"):
        fig.add_trace(go.Scatter(x=group["hour"], y=group["demand_count"], mode="lines+markers", name=name, line=dict(width=3.2, color=BRAND_TEAL if name == "Weekend" else BRAND_BLUE), marker=dict(size=6), hovertemplate=f"{name}<br>Hour %{{x}}:00<br>Service demand %{{y:,.0f}}<extra></extra>"))
    if not plot.empty:
        peak = plot.loc[plot["demand_count"].idxmax()]
        peak_info = {"hour": int(peak["hour"]), "context": str(peak["period_type"]), "demand": float(peak["demand_count"])}
        fig.add_annotation(x=peak["hour"], y=peak["demand_count"], text=f"Peak {int(peak['hour'])}:00", showarrow=True, arrowhead=2, ax=35, ay=-35, bgcolor="rgba(255,255,255,.92)", bordercolor="#cbd5e1", font=dict(size=12, color="#132033"))
    fig.update_layout(height=390, margin=dict(l=4,r=8,t=8,b=4), xaxis=dict(title="Hour of day", tickmode="linear", dtick=2), yaxis=dict(title="Service demand"), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), paper_bgcolor="white", plot_bgcolor="white")
    return fig, peak_info

def day_chart(dow: pd.DataFrame, period_type: str) -> go.Figure:
    filtered = apply_period_type(dow, period_type)
    plot = filtered.groupby(["weekday","weekday_name"], as_index=False)["demand_count"].sum().sort_values("weekday")
    order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    plot["weekday_name"] = pd.Categorical(plot["weekday_name"], categories=order, ordered=True)
    plot = plot.sort_values("weekday_name")
    fig = go.Figure(go.Bar(x=plot["weekday_name"].astype(str), y=plot["demand_count"], marker=dict(color="#2f8f9d"), text=[compact_int(v) for v in plot["demand_count"]], textposition="outside", hovertemplate="%{x}<br>Service demand %{y:,.0f}<extra></extra>"))
    fig.update_layout(height=370, margin=dict(l=4,r=8,t=8,b=4), xaxis=dict(title=""), yaxis=dict(title="Service demand"), paper_bgcolor="white", plot_bgcolor="white", showlegend=False)
    return fig

def category_chart(category: pd.DataFrame, start: str, end: str) -> go.Figure:
    data = period_filter(category, start, end) if "period" in category.columns else category.copy()
    plot = data.groupby("service_category", as_index=False)["sample_demand_count"].sum().sort_values("sample_demand_count", ascending=False).head(12).sort_values("sample_demand_count")
    fig = go.Figure(go.Bar(x=plot["sample_demand_count"], y=plot["service_category"], orientation="h", marker=dict(color="#345995"), text=[compact_int(v) for v in plot["sample_demand_count"]], textposition="outside", cliponaxis=False, hovertemplate="%{y}<br>Sample service demand %{x:,.0f}<extra></extra>"))
    fig.update_layout(height=470, margin=dict(l=4,r=60,t=8,b=4), xaxis=dict(title="Sample service demand"), yaxis=dict(title=""), paper_bgcolor="white", plot_bgcolor="white")
    return fig

def weather_chart(weather: pd.DataFrame, view: str) -> go.Figure:
    data = weather[weather["view"] == view].copy()
    if data.empty:
        return go.Figure()
    data["demand_count"] = pd.to_numeric(data["demand_count"], errors="coerce").fillna(0)
    plot = (
        data.groupby("band", as_index=False)["demand_count"]
        .sum()
        .sort_values("demand_count", ascending=False)
    )
    color = "#5f7f91" if view.startswith("Precip") else "#a37353"
    fig = go.Figure(
        go.Bar(
            x=plot["band"],
            y=plot["demand_count"],
            width=0.72,
            marker=dict(color=color, opacity=1.0, line=dict(width=0)),
            text=[compact_int(v) for v in plot["demand_count"]],
            textposition="outside",
            textfont=dict(size=10, color="#8a96a8"),
            cliponaxis=False,
            hovertemplate="%{x}<br>Weather-joined demand %{y:,.0f}<extra></extra>",
        )
    )
    fig.update_layout(
        height=390,
        margin=dict(l=8, r=10, t=24, b=118),
        bargap=0.12,
        xaxis=dict(title="", tickangle=35, tickfont=dict(size=11, color="#8a96a8")),
        yaxis=dict(title="Weather-joined demand", gridcolor="#edf2f7", zerolinecolor="#d9e2ec"),
        paper_bgcolor="white",
        plot_bgcolor="white",
        showlegend=False,
        uniformtext=dict(minsize=9, mode="show"),
    )
    return fig

def main() -> None:
    kpis = load_json("dashboard_kpis.json"); qa = load_json("qa_lineage.json")
    zone_all = load_csv("zone_summary.csv"); zone_period = load_csv("zone_summary_by_period.csv")
    hourly = load_csv("hourly_demand.csv"); dow = load_csv("day_of_week_demand.csv"); heatmap = load_csv("day_hour_heatmap.csv")
    category = load_csv("service_category_mix.csv"); weather = load_csv("weather_context_summary.csv")
    if not kpis or zone_period.empty or hourly.empty or heatmap.empty:
        st.error("Dashboard assets are missing or incomplete. Run `python -u src/dashboard/build_dashboard_assets.py` first."); st.stop()

    hero(kpis)
    with st.sidebar:
        st.markdown("### Dashboard Proof"); st.write(f"Spark `{kpis.get('spark_version')}`"); st.write(f"Zone-hour rows `{fmt_int(kpis.get('zone_hour_records'))}`"); st.write("No full fact-table load at render time.")

    periods = kpis.get("periods") or sorted(hourly["period"].dropna().astype(str).unique().tolist())
    portfolio_mode = st.toggle("Portfolio View", value=True, help="Prioritize the first-screen command-center screenshot layout.")
    with st.expander("Filters & Scenario View", expanded=not portfolio_mode):
        c1, c2, c3 = st.columns([1,1,1])
        choices = ["All time", *periods]
        with c1: start_choice = st.selectbox("Start period", choices, index=0)
        with c2: end_choice = st.selectbox("End period", choices, index=0)
        with c3: period_type = st.radio("Weekday / weekend", ["All", "Weekday", "Weekend"], horizontal=True)
        st.caption("Time range filter applies to dashboard assets generated from the Spark zone-hour planning layer.")

    start_period = periods[0] if start_choice == "All time" else start_choice
    end_period = periods[-1] if end_choice == "All time" else end_choice
    if start_period > end_period: start_period, end_period = end_period, start_period
    is_filtered = start_period != periods[0] or end_period != periods[-1]
    view_filtered = is_filtered or period_type != "All"
    selected_label = "All time" if not is_filtered else f"{start_period} to {end_period}"

    zone_period_f = period_filter(zone_period, start_period, end_period)
    hourly_f = period_filter(hourly, start_period, end_period)
    dow_f = period_filter(dow, start_period, end_period)
    heatmap_f = period_filter(heatmap, start_period, end_period)
    weather_f = period_filter(weather, start_period, end_period)
    zone_current = aggregate_zone_period(zone_period_f, heatmap_f, period_type)
    if zone_current.empty: zone_current = zone_all.copy()
    hourly_fig, peak_info = hourly_chart(hourly_f, period_type)

    selected_demand = zone_current["total_service_demand"].sum()
    selected_zone_hour_records = zone_current["zone_hour_records"].sum()
    top_zone = zone_current.iloc[0]["zone_id"] if not zone_current.empty else "Unavailable"
    peak_hour_label = f"{peak_info['hour']:02d}:00" if peak_info.get("hour") is not None else "Unavailable"
    date_value = selected_label if is_filtered else f"{str(kpis.get('date_start'))[:4]}-{str(kpis.get('date_end'))[:4]}"
    service_label = "Service demand in selected period" if is_filtered else ("Service demand in selected view" if period_type != "All" else "Cleaned service events")
    service_value = compact_int(selected_demand) if view_filtered else compact_int(kpis.get("cleaned_input_events"))
    zh_label = "Zone-hour records selected" if view_filtered else "Zone-hour planning records"

    kpi_grid([
        ("Raw/source records", compact_int(kpis.get("raw_source_rows")), "Source rows audited before event-level collapse"),
        (service_label, service_value, "Spark zone-hour demand total" if is_filtered else "Unique event IDs in cleaned input"),
        (zh_label, compact_int(selected_zone_hour_records if view_filtered else kpis.get("zone_hour_records")), "Planning records from Spark zone-hour layer"),
        ("Active zones/beats", fmt_int(zone_current["zone_id"].nunique()), "Zones active in selected period"),
        ("Date range", date_value, "Selected period" if is_filtered else f"{kpis.get('date_start')} to {kpis.get('date_end')}"),
        ("Top workload zone", str(top_zone), "Highest service demand in current view"),
        ("Peak demand hour", peak_hour_label, f"{peak_info.get('context')} demand window"),
        ("Mapped beat polygons", fmt_int(kpis.get("mapped_beat_polygons", 55)), "GeoJSON coverage, not full analytic layer"),
    ])

    st.markdown("---")
    map_col, side_col = st.columns([1.75, 1.0], gap="large")
    with map_col:
        with st.container(border=True): render_map(zone_current, int(kpis.get("active_zones_beats") or 156))
    with side_col:
        with st.container(border=True):
            section_title("Highest Workload Zones", "Top zones by service demand for selected time range")
            st.plotly_chart(top_zone_chart(zone_current, 10), use_container_width=True)
        st.markdown(f"""
        <div class="insight-card"><div class="insight-label">Peak Demand Window</div><div class="insight-value">{peak_hour_label}</div><div class="insight-text">{peak_info.get('context')} workload peak. Highest average service demand occurs during the midday operating window.</div></div>
        <div class="qa-card"><div class="insight-label" style="color:#9db2ca;">PySpark proof</div><div class="muted"><b>Full run</b> - Spark {kpis.get('spark_version')} - pandas fallback disabled</div></div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    with st.container(border=True):
        section_title("Zone-Hour Workload Intensity", "Top workload zones by hour of day for selected time range")
        st.plotly_chart(heatmap_chart(heatmap_f, zone_current, period_type, portfolio_mode), use_container_width=True)

    st.markdown("---")
    left, right = st.columns([1.22, 1.0], gap="large")
    with left:
        with st.container(border=True):
            section_title("Daily Demand Rhythm", "Service demand by hour of day for selected time range")
            st.plotly_chart(hourly_fig, use_container_width=True)
    with right:
        with st.container(border=True):
            section_title("Weekly Workload Pattern", "Total service demand by day for selected time range")
            st.plotly_chart(day_chart(dow_f, period_type), use_container_width=True)

    st.markdown("---")
    cat_col, weather_col = st.columns([1.05, 1.15], gap="large")
    with cat_col:
        with st.container(border=True):
            section_title("Service Category Mix", "Top categories in sampled fact events")
            if category.empty: st.info("No service-category sample asset is available.")
            else:
                st.plotly_chart(category_chart(category, start_period, end_period), use_container_width=True)
                st.caption("Sample-based category mix from `fact_service_events_sample.csv`; period filter applies only to the 50k-row sample asset.")
    with weather_col:
        with st.container(border=True):
            section_title("Weather-Context Demand", "Descriptive view using weather-joined records only; not causal inference.")
            st.caption("Weather context covers 25.15% of events due to the overlap between available weather history and the full 2009-2026 service-event timeline. Weather views are descriptive only. The selected time range is applied before records are grouped into weather-band bars.")
            if weather_f.empty: st.info("No weather-context rows match the selected period.")
            else:
                w1, w2 = st.columns(2)
                with w1: st.plotly_chart(weather_chart(weather_f, "Precipitation band"), use_container_width=True)
                with w2: st.plotly_chart(weather_chart(weather_f, "Temperature band"), use_container_width=True)

    st.markdown("---")
    with st.container(border=True):
        section_title("QA / Data Lineage", "Full-transform proof and known enrichment-join limitation")
        q1, q2, q3, q4 = st.columns(4)
        q1.metric("Spark", str(qa.get("spark_version", "4.1.2"))); q2.metric("Input cleaned events", fmt_int(qa.get("cleaned_input_events")))
        q3.metric("Zone-hour rows", fmt_int(qa.get("zone_hour_records"))); q4.metric("Pandas fallback", str(qa.get("pandas_fallback_used", False)))
        st.markdown("Post-enrichment QA found **149 duplicate fact rows** across **6.47M cleaned events**. Unique event IDs matched the cleaned input exactly, with no missing or newly created event IDs. This is documented as a minor enrichment-join limitation.")
        details = pd.DataFrame([
            ["Java runtime", qa.get("java_version")], ["Fact rows", fmt_int(qa.get("fact_output_rows"))], ["Unique event IDs", fmt_int(qa.get("unique_event_ids"))],
            ["Duplicate fact rows", fmt_int(qa.get("post_enrichment_duplicate_fact_rows"))], ["Duplicate impact", fmt_pct(qa.get("post_enrichment_duplicate_impact"), 4)],
            ["Weather join coverage", fmt_pct(qa.get("weather_join_coverage"))], ["No missing or fake event IDs", "Confirmed in Spark QA"]
        ], columns=["Lineage item", "Value"])
        st.dataframe(details, use_container_width=True, hide_index=True)

if __name__ == "__main__":
    main()
