from __future__ import annotations

import pandas as pd

from src import config
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


def _norm_cols(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).strip().lower().replace("__", "_") for c in out.columns]
    return out


def clean_geography() -> None:
    config.ensure_directories()
    beats = _norm_cols(pd.read_csv(config.BEATS_CSV_PATH))
    if "beat" not in beats:
        raise ValueError("Beat lookup must include a beat column.")
    beats["zone_id"] = beats["beat"].astype("string").str.upper().str.strip()
    beats["beat"] = beats["zone_id"]
    if "first_precinct" in beats:
        beats["precinct"] = beats["first_precinct"].astype("string").str.upper()
    elif "precinct" not in beats:
        beats["precinct"] = pd.NA
    beats["sector"] = beats.get("sector", pd.Series(pd.NA, index=beats.index)).astype("string").str.upper()
    lookup_cols = [c for c in ["zone_id", "beat", "precinct", "sector", "shape_area", "shape_length", "objectid"] if c in beats]
    beats[lookup_cols].to_csv(config.CLEANED_BEATS_CSV, index=False)

    map_ready = beats[lookup_cols].copy()
    try:
        import geopandas as gpd

        gdf = gpd.read_file(config.BEATS_GEOJSON_PATH)
        gdf.columns = [str(c).strip().lower() for c in gdf.columns]
        gdf["zone_id"] = gdf["beat"].astype("string").str.upper().str.strip()
        if gdf.crs is None:
            gdf = gdf.set_crs("EPSG:2926")
        centroids = gpd.GeoSeries(gdf.geometry.centroid, crs=gdf.crs).to_crs("EPSG:4326")
        gdf_wgs = gdf.to_crs("EPSG:4326")
        geo = pd.DataFrame(
            {
                "zone_id": gdf["zone_id"],
                "centroid_longitude": centroids.x,
                "centroid_latitude": centroids.y,
                "geometry_wkt": gdf_wgs.geometry.to_wkt(),
            }
        )
        map_ready = map_ready.merge(geo, on="zone_id", how="left")
        logger.info("GeoJSON processed with geopandas")
    except Exception as exc:
        map_ready["centroid_longitude"] = pd.NA
        map_ready["centroid_latitude"] = pd.NA
        map_ready["geometry_wkt"] = pd.NA
        logger.warning("GeoJSON geometry could not be projected; properties-only output written. Reason: %s", exc)

    map_ready.to_csv(config.TABLEAU_OUTPUT_DIR / "tableau_geo_map.csv", index=False)
    logger.info("Wrote cleaned geography lookup and map-ready CSV")


if __name__ == "__main__":
    clean_geography()
