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
import osmnx as ox
import networkx as nx

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

            df_stops["school"] = df_stops["school"].astype(str).str.strip()
            schools = sorted(df_stops["school"].dropna().unique())
            selected_school = st.sidebar.selectbox("Select a school", schools)
            df_stops = df_stops[df_stops["school"] == selected_school].copy()

            try:
                school_geocode = gmaps.geocode(selected_school)
                if school_geocode:
                    loc = school_geocode[0]["geometry"]["location"]
                    st.session_state["school_coords"] = (loc["lat"], loc["lng"])
            except:
                st.warning("⚠️ Could not geocode school.")
        else:
            df_stops = df_uploaded
    else:
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

# === STEP 2: Geocode if missing lat/lon ===
if "lat" not in df_stops.columns or "lon" not in df_stops.columns:
    if "Address" in df_stops.columns:
        addresses = df_stops["Address"].fillna("").astype(str).tolist()
        lats, lons = geocode_addresses(addresses)
        df_stops["lat"] = lats
        df_stops["lon"] = lons
    else:
        st.error("No coordinates or Address found.")
        st.stop()

# === STEP 3: Drop invalid coordinates
df_stops = df_stops.dropna(subset=["lat", "lon"])

# === STEP 4: Safety scoring
with st.spinner("Scoring stops..."):
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
    st.error(f"Map error: {e}")

# === ROUTE GENERATION ===
st.subheader("🗺️ Route Planner")

if st.button("Generate Routes"):
    try:
        school_coords = st.session_state.get("school_coords")
        if not school_coords:
            st.error("No school location found.")
        else:
            with st.spinner("Generating road-based routes..."):
                routes, G, clustered_stops = cluster_and_route_stops(df_stops.copy(), school_coords, n_clusters=4)
                st.session_state["routes"] = routes
                st.session_state["G"] = G
                st.session_state["clustered_stops"] = clustered_stops
                st.success(f"✅ Generated {len(routes)} clustered routes.")
    except Exception as e:
        st.error(f"Routing error: {e}")

# === DISPLAY ROUTES ===
if "routes" in st.session_state and "G" in st.session_state:
    st.subheader("📍 Optimized Route Map")
    routes = st.session_state["routes"]
    G = st.session_state["G"]
    depot = st.session_state["school_coords"]

    # DEBUGGING OUTPUT
    st.write("✅ Number of routes:", len(routes))
    for rid, path in routes.items():
        st.write(f"Route {rid} → nodes: {path[:5]}...")

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
            edge_gdf = ox.graph.to_gdfs(G.subgraph(full_path), nodes=False)
            line = edge_gdf.unary_union
            if line.is_empty:
                continue
            coords = list(line.coords)
            folium.PolyLine(coords, color="blue", weight=4, tooltip=f"Route {rid}").add_to(m)
        except Exception as e:
            st.warning(f"Route {rid} drawing failed: {e}")

    st_folium(m, width=950, height=600)

# === STOP TABLE ===
st.subheader("📋 Stop Table")
st.dataframe(df_stops)
