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

# === STEP 1: Load Stops ===
st.sidebar.header("1. Load Stops")
mode = st.sidebar.radio("Choose input mode:", ["Upload CSV", "Simulate from School Name"])
df_stops = None

if mode == "Upload CSV":
    uploaded = st.sidebar.file_uploader("Upload stop CSV", type="csv")

    if uploaded:
        df_uploaded = pd.read_csv(uploaded)
        df_uploaded.columns = df_uploaded.columns.str.strip().str.lower()
        st.warning(f"📋 Columns in uploaded file: {list(df_uploaded.columns)}")

        if "home address" in df_uploaded.columns and "city" in df_uploaded.columns:
            df_stops = preprocess_excel_style_sheet(df_uploaded)

            if "school" not in df_stops.columns:
                st.error("❌ 'School' column not found after processing. Please check the format.")
                st.stop()

            df_stops["school"] = df_stops["school"].astype(str).str.strip()
            schools = sorted(df_stops["school"].dropna().unique())

            selected_school = st.sidebar.selectbox("Select a school to process", schools)
            df_stops = df_stops[df_stops["school"] == selected_school].copy()

            try:
                school_geocode = gmaps.geocode(selected_school)
                if school_geocode:
                    loc = school_geocode[0]["geometry"]["location"]
                    st.session_state["school_coords"] = (loc["lat"], loc["lng"])
                else:
                    st.warning("⚠️ Could not geocode selected school.")
            except Exception as e:
                st.warning(f"⚠️ Geocoding error for school: {e}")

            st.success(f"✅ Now processing {len(df_stops)} stops for: {selected_school}")

        else:
            df_stops = df_uploaded
            st.success("✅ Uploaded preformatted stop CSV.")
    else:
        try:
            df_stops = pd.read_csv("sample_stops.csv")
            st.warning("📄 Using sample_stops.csv")
        except:
            st.error("❌ No file available.")
            st.stop()

elif mode == "Simulate from School Name":
    school = st.sidebar.text_input("Enter school name", "")
    n_stops = st.sidebar.slider("Number of stops to simulate", 20, 100, 50)
    simulate_clicked = st.sidebar.button("Simulate Stops")

    if simulate_clicked:
        if not school.strip():
            st.error("❌ Please enter a school name.")
            st.stop()
        try:
            df_stops = generate_stops_for_school(school, n=n_stops)
            st.session_state["df_stops"] = df_stops
            st.session_state["school_coords"] = (df_stops["lat"].mean(), df_stops["lon"].mean())
            st.success(f"✅ Simulated {len(df_stops)} stops for: {school}")
        except Exception as e:
            st.error(f"❌ Simulation failed: {e}")
            st.stop()
    elif "df_stops" in st.session_state:
        df_stops = st.session_state["df_stops"]
    else:
        st.info("📍 Enter a school name and click 'Simulate Stops'")
        st.stop()
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
