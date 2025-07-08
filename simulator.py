# simulator.py

import pandas as pd
import numpy as np
import pyproj
import time
import googlemaps
import streamlit as st
import osmnx as ox

from shapely.geometry import Point
from shapely.ops import transform
from utils import geocode_address, get_district_geometry, generate_weighted_stops

# === CONFIG ===
DEFAULT_UTM = 26917
gmaps = googlemaps.Client(key=st.secrets["google"]["maps_api_key"])


# === STEP 1: Main simulation ===
def simulate_district(school_name, n_stops=50):
    # Geocode the school
    lat, lon = geocode_address(school_name)
    school_point = Point(lon, lat)

    # Get the school district geometry
    district_polygon, district_name, _ = get_district_geometry(lat, lon)

    # Generate realistic stop locations from building centroids
    stops_df = generate_weighted_stops(district_polygon, (lat, lon), n=n_stops)

    # Convert to UTM points for projection logic
    transformer = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{DEFAULT_UTM}", always_xy=True).transform
    stops_utm = [Point(transformer(pt[1], pt[0])) for pt in zip(stops_df["lat"], stops_df["lon"])]

    return {
        "school": school_point,
        "district": district_polygon,
        "stops": stops_utm,
        "utm_crs": DEFAULT_UTM,
        "metadata": {
            "school_name": school_name,
            "district_name": district_name,
            "num_stops": len(stops_df)
        }
    }


# === STEP 2: Reverse geocoding helper ===
def reverse_geocode(lat, lon):
    try:
        result = gmaps.reverse_geocode((lat, lon))
        if result and "formatted_address" in result[0]:
            return result[0]["formatted_address"]
    except Exception as e:
        print(f"Reverse geocoding failed: {e}")
    return "Unknown Address"


# === STEP 3: Score traffic risk based on road proximity ===
def estimate_traffic_risk(lat, lon):
    try:
        point = Point(lon, lat)
        buffer_dist = 75  # meters
        roads = ox.geometries_from_point((lat, lon), tags={"highway": True}, dist=buffer_dist)

        if roads.empty:
            return 0.3  # No roads = low risk

        road_types = roads["highway"].dropna().tolist()
        all_types = []

        for r in road_types:
            if isinstance(r, list):
                all_types.extend(r)
            else:
                all_types.append(r)

        score = 0.3
        for rtype in all_types:
            rtype = str(rtype).lower()
            if "motorway" in rtype:
                return 1.0
            elif "primary" in rtype:
                score = max(score, 0.8)
            elif "secondary" in rtype:
                score = max(score, 0.6)
            elif "tertiary" in rtype:
                score = max(score, 0.5)
            elif "residential" in rtype:
                score = max(score, 0.3)

        return score
    except Exception as e:
        print(f"[Traffic Risk ERROR] {e}")
        return 0.5

# === STEP 4: Final generation wrapper ===
def generate_stops_for_school(school_name, n=50):
    sim = simulate_district(school_name, n_stops=n)
    project_back = pyproj.Transformer.from_crs(sim["utm_crs"], "EPSG:4326", always_xy=True).transform
    stops_latlon = [transform(project_back, pt) for pt in sim["stops"]]

    lats = [pt.y for pt in stops_latlon]
    lons = [pt.x for pt in stops_latlon]

    addresses, risks = [], []

    with st.spinner("🗺️ Reverse geocoding & scoring traffic risk..."):
        for lat, lon in zip(lats, lons):
            addr = reverse_geocode(lat, lon)
            risk = estimate_traffic_risk(lat, lon)
            addresses.append(addr)
            risks.append(risk)
            time.sleep(0.1)

    return pd.DataFrame({
        "lat": lats,
        "lon": lons,
        "Stop Name": [f"Stop {i+1}" for i in range(len(lats))],
        "Address": addresses,
        "Traffic Risk (T)": risks
    })
