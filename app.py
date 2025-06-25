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
                longitudes.append(loc["lon"])
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
        df_stops = pd.read_csv(uploaded)
        st.success("✅ File uploaded!")
    else:
        try:
            df_stops = pd.read_csv("sample_stops.csv")
            st.warning("📄 Using sample_stops.csv")
        except:
            st.error("❌ No file available.")
            st.stop()

elif mode == "Simulate from School Name":
    school = st.sidebar.text_input("Enter school name", "Northville High School, MI")
    n_stops = st.sidebar.slider("Number of stops to simulate", 20, 100, 50)
    simulate_clicked = st.sidebar.button("Simulate Stops")

    if simulate_clicked:
        try:
            df_stops = generate_stops_for_school(school, n=n_stops)
            if df_stops.empty:
                st.error("❌ Simulation returned no stops.")
                st.stop()
            st.success(f"✅ Simulated {len(df_stops)} stops for: {school}")
            st.dataframe(df_stops.head())
            st.session_state["df_stops"] = df_stops
        except Exception as e:
            st.error(f"❌ Simulation failed: {e}")
            st.stop()
    elif "df_stops" in st.session_state:
        df_stops = st.session_state["df_stops"]
    else:
        st.info("📍 Enter a school name and click 'Simulate Stops'")
        st.stop()

# === Step 2: Add missing coordinates from Address ===
if "lat" not in df_stops.columns or "lon" not in df_stops.columns:
    if "Address" in df_stops.columns:
        addresses = df_stops["Address"].fillna("").astype(str)
        lats, lons = geocode_addresses(addresses)

        # Safely match DataFrame length
        if len(lats) != len(df_stops) or len(lons) != len(df_stops):
            st.warning("⚠️ Geocoding results mismatched. Trimming to fit.")
            min_len = min(len(df_stops), len(lats))
            df_stops = df_stops.iloc[:min_len].copy()
            df_stops["lat"] = lats[:min_len]
            df_stops["lon"] = lons[:min_len]
        else:
            df_stops["lat"] = lats
            df_stops["lon"] = lons
    else:
        st.error("❌ No lat/lon or Address available for geocoding.")
        st.stop()

# === Clean out bad coordinates ===
df_stops = df_stops.dropna(subset=["lat", "lon"])
df_stops = df_stops[df_stops["lat"].apply(lambda x: isinstance(x, (float, int)))]

# === Step 3: Safety Scoring ===
with st.spinner("🔍 Estimating safety scores..."):
    df_stops = autofill_missing_fields(df_stops)
    df_stops["SES Score"] = df_stops.apply(calculate_ses, axis=1)
    df_stops["Safety Rating"] = df_stops["SES Score"].apply(
        lambda s: "Safe" if s >= 0.7 else "Acceptable" if s >= 0.5 else "Unsafe"
    )

# === Safety Map ===
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
    st.error(f"❌ Map rendering failed: {e}")

# === Fleet Mix Optimizer ===
st.subheader("🚐 Fleet Mix Optimizer")
bus_capacity = 20
van_capacity = 7
bus_cost = 200
van_cost = 120
driver_cost = 150

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
        buses, vans, drivers = best_mix
        st.success(f"✅ Optimal Fleet: {buses} Buses, {vans} Vans")
        st.markdown(f"- **Drivers Needed:** {drivers}")
        st.markdown(f"- **Estimated Daily Cost:** `${lowest_cost:,.2f}`")
        st.markdown(f"- **Total Capacity:** {buses * bus_capacity + vans * van_capacity}")
    else:
        st.error("❌ No valid fleet mix found.")

# === Coverage Summary ===
st.subheader("🧭 Route Coverage Summary")
st.write(f"🔴 Unsafe Stops: {df_stops[df_stops['Safety Rating']=='Unsafe'].shape[0]}")
st.write(f"🟠 Acceptable Stops: {df_stops[df_stops['Safety Rating']=='Acceptable'].shape[0]}")
st.write(f"🟢 Safe Stops: {df_stops[df_stops['Safety Rating']=='Safe'].shape[0]}")

# === Stop Table ===
st.subheader("📋 Stop Table")
st.dataframe(df_stops, use_container_width=True)
