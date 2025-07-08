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
    lat, lon = geocode_address(school_name)
    school_point = Point(lon, lat)
    district_polygon, district_name, _ = get_district_geometry(lat, lon)
    stops_df = generate_weighted_stops(district_polygon, (lat, lon), n=n_stops)

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
        print(f"[Reverse Geocode ERROR] {e}")
    return "Unknown Address"


# === STEP 3: Estimate traffic risk based on OSM roads ===
def estimate_traffic_risk(lat, lon):
    try:
        print(f"[DEBUG] Estimating traffic risk at ({lat}, {lon})")
        point = Point(lon, lat)
        buffer_dist = 75

        roads = ox.features_from_point((lat, lon), tags={"highway": True}, dist=buffer_dist)
        print(f"[DEBUG] Found {len(roads)} road segments")

        if roads.empty:
            return 0.3

        road_types = roads["highway"].dropna().tolist()
        print(f"[DEBUG] Raw road types: {road_types}")

        all_types = []
        for r in road_types:
            all_types.extend(r if isinstance(r, list) else [r])

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


# === STEP 4: Detect if U-turn is needed ===
def detect_uturn_needed(origin_lat, origin_lon, dest_lat, dest_lon):
    print(f"[U-Turn DEBUG] Checking U-turn from stop ({origin_lat}, {origin_lon}) to school ({dest_lat}, {dest_lon})")
    directions = gmaps.directions((origin_lat, origin_lon), (dest_lat, dest_lon), mode="driving")

    if not directions:
        print("[U-Turn DEBUG] No directions found")
        return False

    steps = directions[0]['legs'][0]['steps']
    for step in steps:
        maneuver = step.get('maneuver', '').lower()
        instruction = step.get('html_instructions', '').lower()
        print("[U-Turn DEBUG] Instruction:", instruction)
        print("[U-Turn DEBUG] Maneuver:", maneuver)

        if "u-turn" in instruction or "uturn" in maneuver:
            print("[U-Turn DETECTED]")
            return True

    print("[U-Turn DEBUG] No U-turn detected")
    return False


# === STEP 5: Final generation wrapper ===
def generate_stops_for_school(school_name, n=50):
    sim = simulate_district(school_name, n_stops=n)
    project_back = pyproj.Transformer.from_crs(sim["utm_crs"], "EPSG:4326", always_xy=True).transform
    stops_latlon = [transform(project_back, pt) for pt in sim["stops"]]

    lats = [pt.y for pt in stops_latlon]
    lons = [pt.x for pt in stops_latlon]

    addresses, risks, uturns = [], [], []

    school_lat = sim["school"].y
    school_lon = sim["school"].x

    with st.spinner("🗺️ Reverse geocoding, traffic risk, U-turn detection..."):
        for lat, lon in zip(lats, lons):
            addr = reverse_geocode(lat, lon)
            risk = estimate_traffic_risk(lat, lon)
            needs_uturn = detect_uturn_needed(lat, lon, school_lat, school_lon)

            addresses.append(addr)
            risks.append(risk)
            uturns.append(1 if needs_uturn else 0)
            time.sleep(0.1)

    return pd.DataFrame({
        "lat": lats,
        "lon": lons,
        "Stop Name": [f"Stop {i+1}" for i in range(len(lats))],
        "Address": addresses,
        "Traffic Risk (T)": risks,
        "U-Turn Required (U)": uturns
    })
