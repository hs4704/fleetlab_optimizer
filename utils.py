# utils.py

import googlemaps
import geopandas as gpd
import pandas as pd
import numpy as np
import pyproj
from shapely.geometry import Point
from shapely.ops import transform
import osmnx as ox
import streamlit as st

# === CONFIG ===
DEFAULT_UTM = 26917  # Michigan UTM zone
gmaps = googlemaps.Client(key=st.secrets["google"]["maps_api_key"])

# === GEOCODING ===
def geocode_address(address):
    geocode = gmaps.geocode(address)
    if not geocode:
        raise ValueError(f"❌ Could not geocode address: {address}")
    loc = geocode[0]['geometry']['location']
    return loc['lat'], loc['lng']

@st.cache_data(show_spinner="📍 Geocoding school address...")
def geocode_school_address(address):
    return geocode_address(address)

# === DISTRICT MATCHING ===
def get_district_geometry(lat, lon, district_geojson="School_District.geojson"):
    districts = gpd.read_file(district_geojson).to_crs(epsg=4326)
    districts = districts[districts.geometry.type.isin(["Polygon", "MultiPolygon"])]

    # Debug info (optional)
    # st.warning(f"📂 GeoJSON geometry types: {districts.geometry.type.unique()}")

    point = Point(lon, lat)
    point_gdf = gpd.GeoDataFrame([{"geometry": point}], crs="EPSG:4326")
    joined = gpd.sjoin(districts, point_gdf, how="inner", predicate="contains")

    if joined.empty:
        raise ValueError("❌ No matching school district found for the selected location.")

    row = joined.iloc[0]
    geometry = row.geometry

    # Debug info (optional)
    # st.warning(f"📐 Matched geometry type: {geometry.geom_type}")
    st.info(f"🎯 Matched district: {row.get('Name', 'Unknown')} (DCode: {row.get('DCode', '0000')})")
    return geometry, row.get("Name", "Unknown"), row.get("DCode", "0000")

# === PROJECTION UTILS ===
def get_transformers():
    fwd = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{DEFAULT_UTM}", always_xy=True).transform
    rev = pyproj.Transformer.from_crs(f"EPSG:{DEFAULT_UTM}", "EPSG:4326", always_xy=True).transform
    return fwd, rev

# === STOP GENERATOR ===
def generate_weighted_stops(district_poly_latlon, school_point_latlon, n=50):
    tags = {"building": True}
    try:
        buildings = ox.features_from_polygon(district_poly_latlon, tags)
    except Exception as e:
        raise ValueError(f"❌ Could not fetch buildings from OpenStreetMap: {e}")

    if buildings.empty:
        raise ValueError("❌ No buildings found in selected district from OpenStreetMap.")

    building_centroids = buildings.centroid
    building_centroids = building_centroids[building_centroids.geometry.notnull()]
    fwd, rev = get_transformers()
    building_centroids_utm = building_centroids.to_crs(epsg=DEFAULT_UTM)

    school_point = Point(school_point_latlon[1], school_point_latlon[0])
    school_utm = transform(fwd, school_point)

    walk_buffer = 400
    filtered = building_centroids_utm[building_centroids_utm.distance(school_utm) > walk_buffer]

    if filtered.empty:
        raise ValueError("❌ All buildings are too close to the school. No valid stops.")

    if len(filtered) < n:
        st.warning(f"⚠️ Only {len(filtered)} stops available beyond walking distance.")
        sampled = filtered
    else:
        sampled = filtered.sample(n=n)

    try:
        stops = [transform(rev, pt) for pt in sampled.geometry]
        latitudes = [p.y for p in stops if np.isfinite(p.y)]
        longitudes = [p.x for p in stops if np.isfinite(p.x)]
        if not latitudes or not longitudes:
            raise ValueError("❌ Coordinate transformation failed.")
    except Exception as e:
        raise ValueError(f"❌ Failed to convert stop coordinates: {e}")

    return pd.DataFrame({"lat": latitudes, "lon": longitudes})

# === SAFETY FACTOR FILLER ===
def autofill_missing_fields(df):
    for idx, row in df.iterrows():
        address = row.get("Address", "Unknown Address")
        lat, lon = row.get("lat"), row.get("lon")

        # === Traffic Risk fallback ===
        if 'Traffic Risk (T)' not in df.columns or pd.isna(row.get('Traffic Risk (T)')):
            df.at[idx, 'Traffic Risk (T)'] = 0.5

        # === U-Turn fallback ===
        if 'U-Turn Required (U)' not in df.columns or pd.isna(row.get('U-Turn Required (U)')):
            df.at[idx, 'U-Turn Required (U)'] = 0

        # === Construction Risk using OSM 'highway=construction' ===
        if 'Construction Risk (C)' not in df.columns or pd.isna(row.get('Construction Risk (C)')):
            try:
                construction = ox.geometries_from_point(
                    (lat, lon),
                    tags={"highway": "construction"},
                    dist=100
                )
                df.at[idx, 'Construction Risk (C)'] = 0.9 if not construction.empty else 0.2
            except Exception as e:
                if "No matching features" not in str(e):
                    print(f"[Construction Risk ERROR] {e}")
                df.at[idx, 'Construction Risk (C)'] = 0.2

        # === Visibility, Lighting, Pedestrian Safety, Sidewalk Quality fallbacks ===
        for col, default in [
            ("Visibility (V)", 0.6),
            ("Lighting (L)", 0.5),
            ("Pedestrian Safety (P)", 0.5),
            ("Sidewalk Quality (S)", 0.5),
        ]:
            if col not in df.columns or pd.isna(row.get(col)):
                df.at[idx, col] = default

    return df

# === SES CALCULATOR ===
def calculate_ses(row):
    weights = {
        "V": 0.20, "L": 0.10, "T": 0.30,
        "P": 0.15, "S": 0.10, "C": 0.10, "U": 0.05
    }
    adjusted = {
        "V": row.get("Visibility (V)", 0.5),
        "L": row.get("Lighting (L)", 0.5),
        "T": 1 - row.get("Traffic Risk (T)", 0.5),
        "P": row.get("Pedestrian Safety (P)", 0.5),
        "S": row.get("Sidewalk Quality (S)", 0.5),
        "C": 1 - row.get("Construction Risk (C)", 0.2),
        "U": 1 - row.get("U-Turn Required (U)", 0)
    }
    return sum(weights[k] * adjusted[k] for k in weights)
