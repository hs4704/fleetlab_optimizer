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
# === OPTIMIZE FLEET MIX ===
st.subheader("🚐 Fleet Mix Optimizer")
bus_capacity = 55
van_capacity = 9
bus_cost = 483  
van_cost = 95 + 8.33 + 16.31  # Total: $199.64
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

# === DISPLAY RESULTS ===
if "fleet_mix" in st.session_state:
    mix = st.session_state["fleet_mix"]
    st.success(f"✅ Optimal Fleet: {mix['buses']} Buses, {mix['vans']} Vans")
    st.markdown(f"- **Drivers Needed:** {mix['drivers']}")
    st.markdown(f"- **Estimated Daily Cost:** ${mix['cost']:,.2f}")
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
    savings_pct = round(100 * savings / baseline_cost, 1)

    num_safe = df_stops[df_stops["Safety Rating"] == "Safe"].shape[0]
    pct_safe = round(100 * num_safe / total_stops, 1)

    st.markdown(f"""
    ### ✅ FleetLab Optimization Results:
    - **Recommended Fleet**: {mix['buses']} Buses, {mix['vans']} Vans  
    - **Drivers Needed**: {mix['drivers']}  
    - **Daily Cost with FleetLab**: ${optimized_cost:,.2f}  
    - **Baseline (All Buses) Cost**: ${baseline_cost:,.2f}  
    - **Daily Savings**: ${savings:,.2f} ({savings_pct}% lower)  
    - **% of Safe Stops**: {pct_safe}%  
    """)
else:
    st.info("ℹ️ Run the Fleet Mix Optimizer to view the summary.")
# === STOP TABLE ===
st.subheader("📋 Stop Table")
st.dataframe(df_stops)
