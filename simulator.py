# simulator.py

import pandas as pd
from shapely.geometry import Point
from shapely.ops import transform
from utils import geocode_address, get_district_geometry, generate_weighted_stops
import pyproj
import googlemaps
import streamlit as st
import time

# Initialize Google Maps client
gmaps = googlemaps.Client(key=st.secrets["google"]["maps_api_key"])

def simulate_district(school_name, n_stops=50):
    # 1. Geocode school location
    lat, lon = geocode_address(school_name)
    school_point = Point(lon, lat)

    # 2. Get school district polygon and projection
    district_polygon, district_name, _ = get_district_geometry(lat, lon)

    # 3. Generate weighted building-based stop locations
    stops_df = generate_weighted_stops(district_polygon, (lat, lon), n=n_stops)

    # 4. Convert stops to shapely Points in UTM
    transformer = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:26917", always_xy=True).transform
    stops_utm = [Point(transformer(pt[1], pt[0])) for pt in zip(stops_df["lat"], stops_df["lon"])]

    return {
        "school": school_point,
        "district": district_polygon,
        "stops": stops_utm,
        "utm_crs": 26917,
        "metadata": {
            "school_name": school_name,
            "district_name": district_name,
            "num_stops": len(stops_df)
        }
    }

def reverse_geocode(lat, lon):
    try:
        result = gmaps.reverse_geocode((lat, lon))
        if result and "formatted_address" in result[0]:
            return result[0]["formatted_address"]
    except Exception as e:
        print(f"Reverse geocoding failed: {e}")
    return "Unknown Address"

def generate_stops_for_school(school_name, n=50):
    sim = simulate_district(school_name, n_stops=n)
    project_back = pyproj.Transformer.from_crs(sim["utm_crs"], "EPSG:4326", always_xy=True).transform
    stops_latlon = [transform(project_back, pt) for pt in sim["stops"]]

    lats = [pt.y for pt in stops_latlon]
    lons = [pt.x for pt in stops_latlon]

    # Reverse geocode all lat/lon points to get stop addresses
    addresses = []
    with st.spinner("🗺️ Reverse geocoding simulated stops..."):
        for lat, lon in zip(lats, lons):
            addr = reverse_geocode(lat, lon)
            addresses.append(addr)
            time.sleep(0.1)  # avoid rate limits

    return pd.DataFrame({
        "lat": lats,
        "lon": lons,
        "Stop Name": [f"Stop {i+1}" for i in range(len(lats))],
        "Address": addresses
    })

    return pd.DataFrame({
        "lat": [pt.y for pt in stops_latlon],
        "lon": [pt.x for pt in stops_latlon],
        "Stop Name": [f"Stop {i+1}" for i in range(len(stops_latlon))],
        "Address": [sim["metadata"]["school_name"]]*len(stops_latlon)
    })
