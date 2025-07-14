# app.py
import streamlit as st
import pandas as pd
import googlemaps
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
import matplotlib.pyplot as plt
import time
from simulator import generate_stops_for_school
from utils import autofill_missing_fields, calculate_ses
from preprocess import preprocess_excel_style_sheet
from router import cluster_and_route_stops, export_routes_geojson
import numpy as np
import base64

# === CONFIG ===
st.set_page_config(page_title="FleetLab Optimizer Demo", layout="wide")
st.title("🚌 FleetLab Routing & Cost Optimizer")

# === GOOGLE MAPS CLIENT ===
gmaps = googlemaps.Client(key=st.secrets["google"]["maps_api_key"])

# === GEOCODER FUNCTION (cached) ===
@st.cache_data(show_spinner="📍 Geocoding addresses...")
def geocode_addresses(addresses):
    latitudes, longitudes = [], []
    for address in addresses:
        try:
            geocode = gmaps.geocode(address)
            if geocode:
                loc = geocode[0]["geometry"]["location"]
                latitudes.append(loc["lat"])
                longitudes.append(loc["lng"])
            else:
                latitudes.append(None)
                longitudes.append(None)
        except:
            latitudes.append(None)
            longitudes.append(None)
        time.sleep(0.2)
    return latitudes, longitudes

# [unchanged: Load Stops, Geocode, Safety scoring, Fleet optimizer, Executive summary]
# Skip to updated routing

# === ROUTE GENERATION ===
st.subheader("🗺️ Route Planner")

if st.button("Generate Routes"):
    if "school_coords" not in st.session_state:
        st.warning("⚠️ School location not available. Cannot generate routes.")
    else:
        depot = st.session_state["school_coords"]
        try:
            with st.spinner("🚐 Clustering and routing stops using OSM..."):
                route_map, route_geojson = cluster_and_route_stops(df_stops.copy(), depot_coords=depot, max_cluster_size=12)
                st.session_state["route_map"] = route_map
                st.session_state["route_geojson"] = route_geojson
                st.success("✅ Routes generated using road-based paths and KMeans clustering!")
        except Exception as e:
            st.error(f"❌ Routing failed: {e}")

# === DISPLAY ROUTES IF PRESENT ===
if "route_map" in st.session_state:
    st.subheader("📍 Optimized Route Map")
    st_folium(st.session_state["route_map"], width=950)

    st.download_button("📥 Download Routes (GeoJSON)", data=st.session_state["route_geojson"], file_name="fleetlab_routes.geojson", mime="application/geo+json")

# ==Summary==
if "df_stops" in locals() or "df_stops" in globals():
    st.subheader("🧭 Route Coverage Summary")
    st.write(f"🔴 Unsafe Stops: {df_stops[df_stops['Safety Rating']=='Unsafe'].shape[0]}")
    st.write(f"🟠 Acceptable Stops: {df_stops[df_stops['Safety Rating']=='Acceptable'].shape[0]}")
    st.write(f"🟢 Safe Stops: {df_stops[df_stops['Safety Rating']=='Safe'].shape[0]}")

    st.subheader("📋 Stop Table")
    st.dataframe(df_stops, use_container_width=True)
else:
    st.info("ℹ️ No stop data loaded. Please upload or simulate stops first.")
