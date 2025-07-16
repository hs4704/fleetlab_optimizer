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
import numpy as np
from sklearn.cluster import KMeans

# === SIMPLE CLUSTERING-BASED ROUTING ===
def simple_route_solver(school_coords, stop_coords, n_routes=3):
    kmeans = KMeans(n_clusters=n_routes, random_state=42).fit(stop_coords)
    labels = kmeans.labels_

    routes = []
    for i in range(n_routes):
        cluster = [pt for idx, pt in enumerate(stop_coords) if labels[idx] == i]
        cluster.sort(key=lambda pt: (pt[0] - school_coords[0])**2 + (pt[1] - school_coords[1])**2)
        route = [school_coords] + cluster + [school_coords]
        routes.append(route)

    return routes

# === PAGE CONFIG ===
st.set_page_config(page_title="FleetLab Optimizer Demo", layout="wide")
st.title("🚌 FleetLab Routing & Cost Optimizer")

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
        df_uploaded.columns = df_uploaded.columns.str.strip()
        if "home address" in df_uploaded.columns.str.lower().tolist():
            df_stops = preprocess_excel_style_sheet(df_uploaded)
        else:
            df_stops = df_uploaded
    else:
        try:
            df_sample = pd.read_csv("sample_stops.csv")
            df_sample.columns = df_sample.columns.str.strip()
            if "Address" in df_sample.columns:
                df_stops = df_sample.copy()
                st.success(f"✅ Loaded fallback: {len(df_stops)} stops from sample_stops.csv")
                st.session_state["school_coords"] = (42.2808, -83.7430)
            else:
                st.error("❌ sample_stops.csv missing 'Address' column.")
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

# === STEP 2: Geocode if missing
if "lat" not in df_stops.columns or "lon" not in df_stops.columns:
    if "Address" in df_stops.columns:
        lats, lons = geocode_addresses(df_stops["Address"].astype(str).tolist())
        df_stops["lat"] = lats
        df_stops["lon"] = lons
    else:
        st.error("❌ No coordinates or address column available.")
        st.stop()

# === STEP 3: Drop invalid coordinates
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
routing_mode = st.radio("Routing Mode", ["Simple Routing"])
if st.button("Generate Routes"):
    school_coords = st.session_state.get("school_coords")
    if not school_coords:
        st.error("⚠️ No school location available.")
    else:
        stop_coords = [
            (lat, lon) for lat, lon in zip(df_stops["lat"], df_stops["lon"])
            if isinstance(lat, (float, int)) and isinstance(lon, (float, int)) and pd.notnull(lat) and pd.notnull(lon)
        ]
        with st.spinner("🧭 Generating simple clustered routes..."):
            try:
                routes = simple_route_solver(school_coords, stop_coords, n_routes=3)
                st.session_state["routes"] = routes
                st.success(f"✅ Generated {len(routes)} simple clustered routes.")
            except Exception as e:
                st.error(f"❌ Routing error: {e}")

# === DISPLAY ROUTES ===
if "routes" in st.session_state:
    st.subheader("📍 Simple Route Map")
    routes = st.session_state["routes"]
    m = folium.Map(location=st.session_state["school_coords"], zoom_start=13)

    colors = ["red", "blue", "green", "purple", "orange"]
    for i, route in enumerate(routes):
        valid_coords = [pt for pt in route if isinstance(pt[0], (float, int)) and isinstance(pt[1], (float, int))]
        if valid_coords:
            folium.PolyLine(valid_coords, color=colors[i % len(colors)], weight=5, tooltip=f"Route {i+1}").add_to(m)
            for j, pt in enumerate(valid_coords):
                folium.CircleMarker(
                    location=pt,
                    radius=4,
                    color=colors[i % len(colors)],
                    fill=True,
                    fill_opacity=0.8,
                    popup=f"R{i+1} - Stop {j}"
                ).add_to(m)

    st_folium(m, width=900, height=600)

# === FINAL STOP TABLE ===
st.subheader("📋 Final Stop Table")
st.dataframe(df_stops, use_container_width=True)
