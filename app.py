# app.py
import streamlit as st
import pandas as pd
import googlemaps
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
import matplotlib.pyplot as plt
import numpy as np
import time

from simulator import generate_stops_for_school
from utils import autofill_missing_fields, calculate_ses
from preprocess import preprocess_excel_style_sheet
from router import solve_routes

# === CONFIG ===
st.set_page_config(page_title="FleetLab Optimizer Demo", layout="wide")
st.title("🚌 FleetLab Routing & Cost Optimizer")

# === GOOGLE MAPS CLIENT ===
gmaps = googlemaps.Client(key=st.secrets["google"]["maps_api_key"])

# === GEOCODER FUNCTION ===
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
                st.error("❌ 'School' column not found after processing.")
                st.stop()

            schools = sorted(df_stops["school"].dropna().unique())
            selected_school = st.sidebar.selectbox("Select a school to process", schools)
            df_stops = df_stops[df_stops["school"] == selected_school].copy()

            try:
                geo = gmaps.geocode(selected_school)
                if geo:
                    loc = geo[0]["geometry"]["location"]
                    st.session_state["school_coords"] = (loc["lat"], loc["lng"])
            except Exception as e:
                st.warning(f"⚠️ Geocoding error: {e}")

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
            if df_stops.empty:
                st.error("❌ Simulation returned no stops.")
                st.stop()
            st.session_state["df_stops"] = df_stops
            st.success(f"✅ Simulated {len(df_stops)} stops for: {school}")
            st.dataframe(df_stops.head())
            st.session_state["school_coords"] = (df_stops["lat"].mean(), df_stops["lon"].mean())
        except Exception as e:
            st.error(f"❌ Simulation failed: {e}")
            st.stop()
    elif "df_stops" in st.session_state:
        df_stops = st.session_state["df_stops"]
    else:
        st.info("📍 Enter a school name and click 'Simulate Stops'")
        st.stop()

# === STEP 2: Geocode if missing lat/lon ===
if "lat" not in df_stops.columns or "lon" not in df_stops.columns:
    if "address" in df_stops.columns:
        addresses = df_stops["address"].fillna("").astype(str).tolist()
        lats, lons = geocode_addresses(addresses)
        if len(lats) != len(df_stops):
            st.error("❌ Geocoding failed.")
            st.stop()
        df_stops["lat"] = lats
        df_stops["lon"] = lons
    else:
        st.error("❌ No coordinates or address found.")
        st.stop()

# === STEP 3: Drop invalid coords ===
df_stops = df_stops.dropna(subset=["lat", "lon"])
df_stops = df_stops[df_stops["lat"].apply(lambda x: isinstance(x, (float, int)))]

# === STEP 4: SES SAFETY SCORING ===
with st.spinner("🔍 Estimating safety scores..."):
    df_stops = autofill_missing_fields(df_stops)
    df_stops["SES Score"] = df_stops.apply(calculate_ses, axis=1)
    df_stops["Safety Rating"] = df_stops["SES Score"].apply(
        lambda s: "Safe" if s >= 0.7 else "Acceptable" if s >= 0.5 else "Unsafe"
    )

# === STEP 5: SAFETY MAP ===
st.subheader("📍 Stop Safety Map")
try:
    m = folium.Map(location=[df_stops["lat"].mean(), df_stops["lon"].mean()], zoom_start=13)
    cluster = MarkerCluster().add_to(m)
    for _, row in df_stops.iterrows():
        color = "green" if row["Safety Rating"] == "Safe" else "orange" if row["Safety Rating"] == "Acceptable" else "red"
        folium.CircleMarker(
            location=[row["lat"], row["lon"]],
            radius=5,
            color=color,
            fill=True,
            fill_opacity=0.7,
            popup=f"{row.get('Stop Name', 'Stop')}: {row['Safety Rating']}"
        ).add_to(cluster)
    st_folium(m, width=900)
except Exception as e:
    st.error(f"❌ Map failed: {e}")

# === STEP 6: FLEET MIX OPTIMIZER ===
st.subheader("🚐 Fleet Mix Optimizer")
bus_capacity = 55
van_capacity = 9
bus_cost = 483
van_cost = 95 + 8.33 + 16.31
driver_cost = 80

if st.button("Optimize Fleet Mix"):
    total_stops = len(df_stops)
    best_mix = None
    lowest_cost = float("inf")

    for buses in range(0, 6):
        for vans in range(1, 10):
            capacity = buses * bus_capacity + vans * van_capacity
            if capacity >= total_stops:
                drivers = buses + vans
                cost = (buses * bus_cost) + (vans * van_cost) + (drivers * driver_cost)
                if cost < lowest_cost:
                    lowest_cost = cost
                    best_mix = (buses, vans, drivers)

    if best_mix:
        st.session_state["fleet_mix"] = {
            "buses": best_mix[0],
            "vans": best_mix[1],
            "drivers": best_mix[2],
            "cost": lowest_cost,
            "capacity": best_mix[0] * bus_capacity + best_mix[1] * van_capacity
        }
    else:
        st.error("❌ No valid fleet mix found.")

if "fleet_mix" in st.session_state:
    mix = st.session_state["fleet_mix"]
    st.success(f"✅ Optimal Fleet: {mix['buses']} Buses, {mix['vans']} Vans")
    st.markdown(f"- **Drivers Needed:** {mix['drivers']}")
    st.markdown(f"- **Estimated Daily Cost:** `${mix['cost']:,.2f}`")
    st.markdown(f"- **Total Capacity:** {mix['capacity']}")

# === EXECUTIVE SUMMARY ===
st.subheader("📊 Executive Summary")
total_stops = len(df_stops)
buses_needed_baseline = int(np.ceil(total_stops / bus_capacity))
baseline_cost = (buses_needed_baseline * bus_cost) + (buses_needed_baseline * driver_cost)

if "fleet_mix" in st.session_state:
    mix = st.session_state["fleet_mix"]
    optimized_cost = mix["cost"]
    savings = baseline_cost - optimized_cost
    savings_pct = round(100 * (savings / baseline_cost), 1)
    total_safe = df_stops[df_stops["Safety Rating"] == "Safe"].shape[0]
    safe_pct = round(100 * total_safe / total_stops, 1)

    st.markdown(f"""
    ### ✅ FleetLab Optimization Results:
    - **Recommended Fleet**: {mix['buses']} Buses, {mix['vans']} Vans  
    - **Drivers Needed**: {mix['drivers']}  
    - **Daily Cost with FleetLab**: `${optimized_cost:,.2f}`  
    - **Baseline (All Buses) Cost**: `${baseline_cost:,.2f}`  
    - **Daily Savings**: `${savings:,.2f}` ({savings_pct}% lower)  
    - **% of Safe Stops**: {safe_pct}%  
    """)
else:
    st.info("ℹ️ Run the Fleet Mix Optimizer to see the full summary.")

# === ROUTING ===
st.subheader("🗺️ Route Planner")
if st.button("Generate Routes"):
    with st.spinner("🧭 Solving routes..."):
        try:
            if "school_coords" not in st.session_state:
                st.warning("⚠️ No school location")
            else:
                depot = st.session_state["school_coords"]
                stop_coords = [(row["lat"], row["lon"]) for _, row in df_stops.iterrows()]
                all_locations = [depot] + stop_coords
                routes = solve_routes(all_locations, num_vehicles=4, depot_index=0)
                if not routes:
                    st.error("❌ Routing failed.")
                else:
                    st.session_state["routes"] = routes
                    st.session_state["all_locations"] = all_locations
                    st.success(f"✅ {len(routes)} routes generated.")
        except Exception as e:
            st.error(f"❌ Routing failed: {e}")

# === ROUTE DISPLAY ===
if "routes" in st.session_state:
    st.subheader("📍 Optimized Route Map")
    m = folium.Map(location=st.session_state["school_coords"], zoom_start=12)
    colors = ["red", "blue", "green", "purple", "orange", "black"]
    for i, route in enumerate(st.session_state["routes"]):
        color = colors[i % len(colors)]
        points = [st.session_state["all_locations"][idx] for idx in route]
        folium.PolyLine(points, color=color, weight=6, opacity=0.85).add_to(m)
        for j, pt in enumerate(points):
            folium.CircleMarker(
                location=pt,
                radius=5,
                color=color,
                fill=True,
                popup=f"Route {i+1} - Stop {j}" if j > 0 else "Depot"
            ).add_to(m)
    st_folium(m, width=950)

# === ROUTE COVERAGE ===
st.subheader("🧭 Route Coverage Summary")
st.write(f"🔴 Unsafe Stops: {df_stops[df_stops['Safety Rating']=='Unsafe'].shape[0]}")
st.write(f"🟠 Acceptable Stops: {df_stops[df_stops['Safety Rating']=='Acceptable'].shape[0]}")
st.write(f"🟢 Safe Stops: {df_stops[df_stops['Safety Rating']=='Safe'].shape[0]}")

# === FINAL TABLE ===
st.subheader("📋 Stop Table")
st.dataframe(df_stops, use_container_width=True)
