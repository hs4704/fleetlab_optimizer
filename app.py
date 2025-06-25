
# app.py

import streamlit as st
import pandas as pd
import googlemaps
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
import matplotlib.pyplot as plt
import time

from simulator import simulate_district, generate_stops_for_school

# === CONFIG ===
st.set_page_config(page_title="FleetLab Optimizer Demo", layout="wide")
st.title("🚌 FleetLab Routing & Cost Optimizer")

# === GOOGLE MAPS SETUP ===
gmaps = googlemaps.Client(key=st.secrets["google"]["maps_api_key"])

# === ADDRESS GEOCODING ===
@st.cache_data(show_spinner="Geocoding addresses...")
def geocode_addresses(addresses):
    latitudes, longitudes = [], []
    for address in addresses:
        try:
            geocode = gmaps.geocode(address)
            if geocode:
                location = geocode[0]['geometry']['location']
                latitudes.append(location["lat"])
                longitudes.append(location["lng"])
            else:
                latitudes.append(None)
                longitudes.append(None)
        except:
            latitudes.append(None)
            longitudes.append(None)
        time.sleep(0.2)
    return latitudes, longitudes

# === SAFETY FACTORS ===
def autofill_missing_fields(df):
    for idx, row in df.iterrows():
        address = row.get("Address", "Unknown Address")
        if 'Traffic Risk (T)' not in df.columns or pd.isna(row.get('Traffic Risk (T)')):
            df.at[idx, 'Traffic Risk (T)'] = 0.5
        if 'U-Turn Required (U)' not in df.columns or pd.isna(row.get('U-Turn Required (U)')):
            try:
                directions = gmaps.directions("school address", address, mode="driving")
                u_turn = any(
                    step.get('maneuver') in ['uturn-left', 'uturn-right']
                    for leg in directions
                    for step in leg['legs'][0]['steps']
                )
                df.at[idx, 'U-Turn Required (U)'] = int(u_turn)
            except:
                df.at[idx, 'U-Turn Required (U)'] = 0
        if 'Construction Risk (C)' not in df.columns or pd.isna(row.get('Construction Risk (C)')):
            df.at[idx, 'Construction Risk (C)'] = 0.2
        if 'Visibility (V)' not in df.columns: df.at[idx, 'Visibility (V)'] = 0.6
        if 'Lighting (L)' not in df.columns: df.at[idx, 'Lighting (L)'] = 0.5
        if 'Pedestrian Safety (P)' not in df.columns: df.at[idx, 'Pedestrian Safety (P)'] = 0.5
        if 'Sidewalk Quality (S)' not in df.columns: df.at[idx, 'Sidewalk Quality (S)'] = 0.5
    return df

def calculate_ses(row):
    weights = {
        "V": 0.25, "L": 0.15, "T": 0.25,
        "P": 0.2,  "S": 0.1,  "C": 0.05, "U": 0.05
    }
    adjusted = {
        "V": row.get("Visibility (V)", 0.5),
        "L": row.get("Lighting (L)", 0.5),
        "T": 1 - row.get("Traffic Risk (T)", 0.5),
        "P": row.get("Pedestrian Safety (P)", 0.5),
        "S": row.get("Sidewalk Quality (S)", 0.5),
        "C": 1 - row.get("Construction Risk (C)", 0.2),
        "U": 1 - row.get("U-Turn Required (U)", 0)
    }
    return sum(weights[k] * adjusted[k] for k in weights)

# === 1. Load Stops ===
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
    if st.sidebar.button("Simulate Stops"):
        try:
            df_stops = generate_stops_for_school(school)
            st.success(f"✅ Simulated stops for: {school}")
        except Exception as e:
            st.error(f"❌ Simulation failed: {e}")
            st.stop()
    else:
        st.stop()

# === Geocode if missing lat/lon ===
if "lat" not in df_stops.columns or "lon" not in df_stops.columns:
    if "Address" in df_stops.columns:
        lat, lon = geocode_addresses(df_stops["Address"])
        df_stops["lat"] = lat
        df_stops["lon"] = lon
    else:
        st.warning("📍 No geolocation info.")
        st.stop()

# === SAFETY SCORING ===
with st.spinner("Scoring stop safety..."):
    df_stops = autofill_missing_fields(df_stops)
    df_stops["SES Score"] = df_stops.apply(calculate_ses, axis=1)
    df_stops["Safety Rating"] = df_stops["SES Score"].apply(
        lambda s: "Safe" if s >= 0.7 else "Acceptable" if s >= 0.5 else "Unsafe"
    )

# === SAFETY MAP ===
st.subheader("📍 Stop Safety Map")
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

# === FLEET OPTIMIZER ===
st.subheader("🚐 Fleet Mix Optimizer")
if st.button("Optimize Fleet Mix"):
    total = len(df_stops)
    bus_cap = 20
    van_cap = 7
    lowest_cost = float('inf')
    best = None
    for buses in range(0, 4):
        for vans in range(1, 7):
            if buses * bus_cap + vans * van_cap >= total:
                cost = buses * 200 + vans * 120
                if cost < lowest_cost:
                    lowest_cost = cost
                    best = (buses, vans)
    if best:
        buses, vans = best
        st.success(f"Recommended: {buses} Buses and {vans} Vans")
        st.markdown(f"💰 Estimated Cost: ${lowest_cost:.2f}")
        st.markdown(f"👨‍✈️ Drivers Needed: {buses + vans}")
        st.markdown(f"📍 Stops Covered: {total}")
    else:
        st.error("❌ No valid combination.")

# === COVERAGE SUMMARY ===
st.subheader("🧭 Route Coverage Summary")
st.write(f"🔴 Unsafe Stops: {df_stops[df_stops['Safety Rating']=='Unsafe'].shape[0]}")
st.write(f"🟠 Acceptable Stops: {df_stops[df_stops['Safety Rating']=='Acceptable'].shape[0]}")
st.write(f"🟢 Safe Stops: {df_stops[df_stops['Safety Rating']=='Safe'].shape[0]}")

# === TABLE ===
st.subheader("📋 Stop Table")
st.dataframe(df_stops, use_container_width=True)
