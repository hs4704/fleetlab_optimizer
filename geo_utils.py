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
DEFAULT_UTM = 26917  # You may change depending on your default region

# === GOOGLE MAPS SETUP ===
gmaps = googlemaps.Client(key=st.secrets["google"]["maps_api_key"])

# === GEOCODING ===
def geocode_school_address(address):
    geocode = gmaps.geocode(address)
    location = geocode[0]['geometry']['location']
    return location['lat'], location['lng']

def geocode_address(address):
    return geocode_school_address(address)

# === DISTRICT LOOKUP ===
def get_district_geometry(lat, lon, district_geojson="School_District.geojson"):
    districts = gpd.read_file(district_geojson)
    districts['DCode'] = districts['DCode'].astype(str).str.zfill(4)
    districts = districts.to_crs(epsg=4326)

    point = Point(lon, lat)
    point_gdf = gpd.GeoDataFrame([{'geometry': point}], crs="EPSG:4326")
    joined = gpd.sjoin(point_gdf, districts, how='left', predicate='within')

    if joined.empty:
        raise ValueError("❌ No matching district found.")

    district_row = joined.iloc[0]
    return district_row['geometry'], district_row['Name'], district_row['DCode']

# === PROJECTION TRANSFORMERS ===
def get_transformers():
    fwd = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{DEFAULT_UTM}", always_xy=True).transform
    rev = pyproj.Transformer.from_crs(f"EPSG:{DEFAULT_UTM}", "EPSG:4326", always_xy=True).transform
    return fwd, rev

# === OSM BUILDING-CENTROID-BASED STOP GENERATOR ===
def generate_weighted_stops(district_polygon_latlon, school_point_latlon, n=50):
    tags = {"building": True}
    buildings = ox.features_from_polygon(district_polygon_latlon, tags)
    building_centroids = buildings.centroid
    building_centroids = building_centroids[building_centroids.geometry.notnull()]

    # Project to UTM
    fwd, rev = get_transformers()
    building_centroids_utm = building_centroids.to_crs(epsg=DEFAULT_UTM)
    school_pt = Point(school_point_latlon[1], school_point_latlon[0])
    school_utm = transform(fwd, school_pt)

    # Filter out buildings too close to school
    walk_buffer = 400  # meters
    filtered = building_centroids_utm[building_centroids_utm.distance(school_utm) > walk_buffer]

    # Sample
    if len(filtered) < n:
        st.warning("⚠️ Not enough valid building points; using all available.")
        sampled = filtered
    else:
        sampled = filtered.sample(n=n)

    stops = [transform(rev, pt) for pt in sampled.geometry]
    return pd.DataFrame({"lat": [p.y for p in stops], "lon": [p.x for p in stops]})
