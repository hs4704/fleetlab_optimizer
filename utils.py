# utils.py
import googlemaps
import geopandas as gpd
import pandas as pd
import numpy as np
import pyproj
from shapely.geometry import Point, Polygon, MultiPolygon, GeometryCollection
from shapely.ops import transform
import osmnx as ox
import streamlit as st

# === CONFIG ===
DEFAULT_UTM = 26917  # Michigan UTM zone

# === GOOGLE MAPS CLIENT ===
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
    # Load GeoJSON and convert to EPSG:4326
    districts = gpd.read_file(district_geojson).to_crs(epsg=4326)

    # Print unique geometry types in the file
    unique_geom_types = districts.geometry.type.unique()
    st.warning(f"📂 GeoJSON geometry types: {unique_geom_types}")

    # Create a Point from lat/lon
    point = Point(lon, lat)
    point_gdf = gpd.GeoDataFrame([{"geometry": point}], crs="EPSG:4326")

    # Spatial join
    joined = gpd.sjoin(point_gdf, districts, how="left", predicate="within")

    if joined.empty:
        raise ValueError("❌ No matching school district found for the selected location.")

    # Get matched row
    row = joined.iloc[0]
    geometry = row.geometry
    st.warning(f"📐 Matched geometry type: {geometry.geom_type}")

    # Handle GeometryCollection if needed
    if geometry.geom_type == "GeometryCollection":
        polys = [g for g in geometry.geoms if g.geom_type in ["Polygon", "MultiPolygon"]]
        if not polys:
            raise ValueError("❌ District boundary contains no usable Polygon or MultiPolygon.")
        geometry = polys[0]

    # Final check
    if not isinstance(geometry, (Polygon, MultiPolygon)):
        raise ValueError("❌ District boundary is not a Polygon or MultiPolygon.")

    st.info(f"🎯 Matched district: {row.get('Name', 'Unknown')} (DCode: {row.get('DCode', '0000')})")
    return geometry, row.get("Name", "Unknown"), row.get("DCode", "0000")
# === PROJECTION TRANSFORMERS ===
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
        raise ValueError("❌ No buildings found within district boundary from OSM.")

    building_centroids = buildings.centroid
    building_centroids = building_centroids[building_centroids.geometry.notnull()]

    # Project to UTM for distance filtering
    fwd, rev = get_transformers()
    building_centroids_utm = building_centroids.to_crs(epsg=DEFAULT_UTM)

    school_point = Point(school_point_latlon[1], school_point_latlon[0])
    school_utm = transform(fwd, school_point)

    walk_buffer = 400  # meters
    filtered = building_centroids_utm[building_centroids_utm.distance(school_utm) > walk_buffer]

    if len(filtered) < n:
        st.warning("⚠️ Not enough valid buildings far from school. Sampling what’s available.")
        sampled = filtered
    else:
        sampled = filtered.sample(n=n)

    # Reproject back to lat/lon
    stops = [transform(rev, pt) for pt in sampled.geometry]
    return pd.DataFrame({
        "lat": [p.y for p in stops],
        "lon": [p.x for p in stops]
    }) 

