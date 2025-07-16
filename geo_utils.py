# geo_utils.py

import googlemaps
import geopandas as gpd
import pandas as pd
import pyproj
from shapely.geometry import Point
from shapely.ops import transform
import osmnx as ox
import streamlit as st

# === CONFIG ===
DEFAULT_UTM = 26917  # Adjust based on your default region (e.g., Michigan)

# === GOOGLE MAPS CLIENT ===
gmaps = googlemaps.Client(key=st.secrets["google"]["maps_api_key"])

# === GEOCODING ===
def geocode_school_address(address):
    geocode = gmaps.geocode(address)
    if not geocode:
        raise ValueError(f"❌ Could not geocode address: {address}")
    loc = geocode[0]['geometry']['location']
    return loc['lat'], loc['lng']

def geocode_address(address):
    return geocode_school_address(address)

# === DISTRICT LOOKUP ===
def get_district_geometry(lat, lon, district_geojson="School_District.geojson"):
    districts = gpd.read_file(district_geojson)
    districts = districts[districts.geometry.notnull()]
    districts['DCode'] = districts['DCode'].astype(str).str.zfill(4)
    districts = districts.to_crs(epsg=4326)

    point = Point(lon, lat)
    point_gdf = gpd.GeoDataFrame([{'geometry': point}], crs="EPSG:4326")

    joined = gpd.sjoin(districts, point_gdf, how='inner', predicate='contains')
    if joined.empty:
        raise ValueError("❌ No matching school district found for the selected location.")

    row = joined.iloc[0]
    st.info(f"🎯 Matched district: {row.get('Name', 'Unknown')} (DCode: {row.get('DCode', '0000')})")
    return row.geometry, row.get("Name", "Unknown"), row.get("DCode", "0000")

# === PROJECTION UTILS ===
def get_transformers():
    fwd = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{DEFAULT_UTM}", always_xy=True).transform
    rev = pyproj.Transformer.from_crs(f"EPSG:{DEFAULT_UTM}", "EPSG:4326", always_xy=True).transform
    return fwd, rev

# === BUILDING-CENTROID STOP GENERATOR ===
def generate_weighted_stops(district_polygon_latlon, school_point_latlon, n=50):
    tags = {"building": True}
    try:
        buildings = ox.features_from_polygon(district_polygon_latlon, tags)
    except Exception as e:
        raise ValueError(f"❌ Could not fetch buildings from OpenStreetMap: {e}")

    if buildings.empty:
        raise ValueError("❌ No buildings found in district polygon.")

    building_centroids = buildings.centroid
    building_centroids = building_centroids[building_centroids.geometry.notnull()]

    fwd, rev = get_transformers()
    building_centroids_utm = building_centroids.to_crs(epsg=DEFAULT_UTM)

    school_point = Point(school_point_latlon[1], school_point_latlon[0])
    school_utm = transform(fwd, school_point)

    walk_buffer = 400  # meters
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
        latitudes = [p.y for p in stops if pd.notna(p.y)]
        longitudes = [p.x for p in stops if pd.notna(p.x)]
        if not latitudes or not longitudes:
            raise ValueError("❌ Coordinate transformation failed.")
    except Exception as e:
        raise ValueError(f"❌ Failed to convert stop coordinates: {e}")

    return pd.DataFrame({"lat": latitudes, "lon": longitudes})
