# app.py
import streamlit as st
import pandas as pd
import googlemaps
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
import time
from simulator import generate_stops_for_school
from utils import autofill_missing_fields, calculate_ses
from preprocess import preprocess_excel_style_sheet
from router import cluster_and_route_stops
import numpy as np
import osmnx as ox
import networkx as nx
from shapely.geometry import LineString, MultiLineString

# === CONFIG ===
st.set_page_config(page_title="FleetLab Optimizer Demo", layout="wide")
st.title("🚌 FleetLab Routing & Cost Optimizer")

# === GOOGLE MAPS CLIENT ===
gmaps = googlemaps.Client(key=st.secrets["google"]["maps_api_key"])

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

        if "home address" in df_uploaded.columns and "city" in df_uploaded.columns:
            df_stops = preprocess_excel_style_sheet(df_uploaded)
        else:
            df_stops = df_uploaded
    else:
        try:
            df_sample = pd.read_csv("sample_stops.csv")
            df_sample.columns = df_sample.columns.str.strip().str.lower()

            if "address" in df_sample.columns:
                df_stops = df_sample.copy()
                st.success(f"✅ Loaded fallback: {len(df_stops)} stops from sample_stops.csv")
                st.session_state["school_coords"] = (42.2808, -83.7430)  # Example: Ann Arbor
            else:
                st.error("❌ sample_stops.csv missing required address column.")
                st.stop()
        except Exception as e:
            st.error(f"❌ Failed to load sample_stops.csv: {e}")
            st.stop()

elif mode == "Simulate from School Name":
    school = st.sidebar.text_input("Enter school name", "")
    n_stops = st.sidebar.slider("Number of stops to simulate", 20, 100, 50)
    simulate_clicked = st.sidebar.button("Simulate Stops")
    if simulate_clicked:
        df_stops = generate_stops_for_school(school, n=n_stops)
        st.session_state["df_stops"] = df_stops
        st.session_state["school_coords"] = (df_stops["lat"].mean(), df_stops["lon"].mean())
    elif "df_stops" in st.session_state:
        df_stops = st.session_state["df_stops"]
    else:
        st.stop()

# === STEP 2: Geocode if lat/lon missing
if "lat" not in df_stops.columns or "lon" not in df_stops.columns:
    if "address" in df_stops.columns:
        addresses = df_stops["address"].astype(str).fillna("").tolist()
        lats, lons = geocode_addresses(addresses)
        df_stops["lat"] = lats
        df_stops["lon"] = lons
    else:
        st.error("❌ No coordinates or address column available for geocoding.")
        st.stop()

# === STEP 3: Drop bad coordinates
df_stops = df_stops.dropna(subset=["lat", "lon"])
df_stops = df_stops[df_stops["lat"].apply(lambda x: isinstance(x, (float, int)))]

# === STEP 4: Safety scoring
with st.spinner("🔍 Calculating SES and safety..."):
    df_stops = autofill_missing_fields(df_stops)
    df_stops["SES Score"] = df_stops.apply(calculate_ses, axis=1)
    df_stops["Safety Rating"] = df_stops["SES Score"].apply(
        lambda s: "Safe" if s >= 0.7 else "Acceptable" if s >= 0.5 else "Unsafe"
    )

# === SAFETY MAP ===
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
            popup=row.get("Stop Name", "Stop")
        ).add_to(cluster)
    st_folium(m, width=900)
except Exception as e:
    st.error(f"❌ Map rendering error: {e}")

# === ROUTE GENERATION ===
st.subheader("🗺️ Route Planner")

if st.button("Generate Routes"):
    try:
        school_coords = st.session_state.get("school_coords")
        if not school_coords:
            st.error("⚠️ No school location found.")
        else:
            with st.spinner("🚐 Routing on road network..."):
                routes, G, clustered_stops = cluster_and_route_stops(df_stops.copy(), school_coords, n_clusters=4)
                st.session_state["routes"] = routes
                st.session_state["G"] = G
                st.session_state["clustered_stops"] = clustered_stops
                st.success(f"✅ Generated {len(routes)} clustered routes.")
    except Exception as e:
        st.error(f"❌ Routing error: {e}")

# === DISPLAY ROUTES ===
if "routes" in st.session_state and "G" in st.session_state:
    st.subheader("📍 Optimized Route Map")
    routes = st.session_state["routes"]
    G = st.session_state["G"]
    depot = st.session_state["school_coords"]

    m = folium.Map(location=depot, zoom_start=13)

    for rid, route_nodes in routes.items():
        full_path = []
        for u, v in zip(route_nodes[:-1], route_nodes[1:]):
            try:
                segment = nx.shortest_path(G, u, v, weight='length')
                full_path += segment[:-1]
            except Exception as e:
                st.warning(f"Route {rid} segment {u} → {v} failed: {e}")
        if route_nodes:
            full_path.append(route_nodes[-1])

        try:
            edge_gdf = ox.graph_to_gdfs(G.subgraph(full_path), nodes=False)
            line = edge_gdf.unary_union

            if isinstance(line, LineString):
                folium.PolyLine(list(line.coords), color="blue", weight=4, tooltip=f"Route {rid}").add_to(m)
            elif isinstance(line, MultiLineString):
                for segment in line.geoms:
                    folium.PolyLine(list(segment.coords), color="blue", weight=4, tooltip=f"Route {rid}").add_to(m)
        except Exception as e:
            st.warning(f"Route {rid} drawing failed: {e}")

    st_folium(m, width=950, height=600)
# === FLEET MIX OPTIMIZER ===
st.subheader("🚐 Fleet Mix Optimizer")

# Vehicle parameters
bus_capacity = 55
van_capacity = 9
bus_cost = 483  
van_cost = 95 + 8.33 + 16.31  # ≈ $199.64
driver_cost = 80

if st.button("Optimize Fleet Mix"):
    total_stops = len(df_stops)
    best_mix = None
    lowest_cost = float("inf")

    for buses in range(0, 6):  # You can adjust max range as needed
        for vans in range(0, 12):
            total_capacity = buses * bus_capacity + vans * van_capacity
            if total_capacity >= total_stops:
                total_drivers = buses + vans
                total_cost = (buses * bus_cost) + (vans * van_cost) + (total_drivers * driver_cost)

                if total_cost < lowest_cost:
                    lowest_cost = total_cost
                    best_mix = {
                        "buses": buses,
                        "vans": vans,
                        "drivers": total_drivers,
                        "cost": round(total_cost, 2),
                        "capacity": total_capacity
                    }

    if best_mix:
        st.session_state["fleet_mix"] = best_mix
        st.success("✅ Best fleet mix calculated!")
    else:
        st.session_state["fleet_mix"] = None
        st.error("❌ Could not find a valid fleet mix.")

# === DISPLAY OPTIMIZED MIX ===
if st.session_state.get("fleet_mix"):
    mix = st.session_state["fleet_mix"]
    st.markdown(f"""
    **Optimal Fleet Mix**
    - 🚌 Buses: {mix['buses']}
    - 🚐 Vans: {mix['vans']}
    - 👨‍✈️ Drivers Needed: {mix['drivers']}
    - 🪙 Estimated Daily Cost: **${mix['cost']:,.2f}**
    - 👥 Total Capacity: {mix['capacity']}
    """)
else:
    st.info("ℹ️ Click 'Optimize Fleet Mix' to calculate.")

# === EXECUTIVE SUMMARY ===
st.subheader("📊 Executive Summary")

# Baseline: All buses only
baseline_buses = int(np.ceil(len(df_stops) / bus_capacity))
baseline_cost = (baseline_buses * bus_cost) + (baseline_buses * driver_cost)

if st.session_state.get("fleet_mix"):
    mix = st.session_state["fleet_mix"]
    optimized_cost = mix["cost"]
    savings = baseline_cost - optimized_cost
    savings_pct = round(100 * savings / baseline_cost, 1)

    safe_stops = df_stops[df_stops["Safety Rating"] == "Safe"].shape[0]
    safe_pct = round(100 * safe_stops / len(df_stops), 1)

    st.markdown(f"""
    ### ✅ FleetLab Cost Benefit
    - **Optimized Daily Cost:** ${optimized_cost:,.2f}
    - **Baseline (All Buses):** ${baseline_cost:,.2f}
    - **Savings:** ${savings:,.2f} ({savings_pct}% reduction)
    - **% Safe Stops:** {safe_pct}%
    """)
else:
    st.info("ℹ️ Run the optimizer to see savings and safety impact.")
# === STOP TABLE ===
st.subheader("📋 Stop Table")
st.dataframe(df_stops)
