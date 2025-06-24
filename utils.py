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
from shapely.geometry import Polygon, MultiPolygon

# === CONFIG ===
DEFAULT_UTM = 26917  # Michigan UTM Zone

# === GOOGLE MAPS SETUP ===
gmaps = googlemaps.Client(key=st.secrets["google"]["maps_api_key"])

# === GENERAL GEOCODING ===
def geocode_address(address):
    geocode = gmaps.geocode(address)
    if not geocode:
        raise ValueError(f"❌ Could not geocode address: {address}")
    loc = geocode[0]['geometry']['location']
    return loc['lat'], loc['lng']

# === SCHOOL GEOCODING (CACHED) ===
@st.cache_data(show_spinner="Geocoding school address...")
def geocode_school_address(address):
    return geocode_address(address)

# === DISTRICT MATCHING ===

def get_district_geometry(lat, lon, district_geojson="School_District.geojson"):
    districts = gpd.read_file(district_geojson)
    districts = districts.to_crs(epsg=4326)

    point = Point(lon, lat)
    point_gdf = gpd.GeoDataFrame([{'geometry': point}], crs="EPSG:4326")
    joined = gpd.sjoin(point_gdf, districts, how='left', predicate='within')

    if joined.empty:
        raise ValueError("❌ No matching school district found for the given location.")

    district_row = joined.iloc[0]
    geometry = district_row['geometry']
    if not isinstance(geometry, (Polygon, MultiPolygon)):
        raise ValueError("❌ District boundary is not a Polygon or MultiPolygon.")

    return geometry, district_row['Name'], district_row['DCode']
# === PROJECTION UTILITIES ===
def get_transformers():
    fwd = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{DEFAULT_UTM}", always_xy=True).transform
    rev = pyproj.Transformer.from_crs(f"EPSG:{DEFAULT_UTM}", "EPSG:4326", always_xy=True).transform
    return fwd, rev

# === STOP GENERATOR ===
def generate_weighted_stops(district_poly_latlon, school_point_latlon, n=50):
    tags = {"building": True}
    buildings = ox.features_from_polygon(district_poly_latlon, tags)
    building_centroids = buildings.centroid
    building_centroids = building_centroids[building_centroids.geometry.notnull()]

    # Project to UTM
    fwd, rev = get_transformers()
    building_centroids_utm = building_centroids.to_crs(epsg=DEFAULT_UTM)
    school_point = Point(school_point_latlon[1], school_point_latlon[0])
    school_utm = transform(fwd, school_point)

    walk_buffer = 400  # meters
    filtered = building_centroids_utm[building_centroids_utm.distance(school_utm) > walk_buffer]

    if len(filtered) < n:
        st.warning("⚠️ Not enough valid building points far from school; sampling what’s available.")
        sampled = filtered
    else:
        sampled = filtered.sample(n=n)

    stops = [transform(rev, pt) for pt in sampled.geometry]
    return pd.DataFrame({"lat": [p.y for p in stops], "lon": [p.x for p in stops]})
        sampled = filtered.sample(n=n)

    stops = [transform(rev, pt) for pt in sampled.geometry]
    return pd.DataFrame({"lat": [p.y for p in stops], "lon": [p.x for p in stops]})
