import streamlit as st
import pandas as pd
import googlemaps
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
import matplotlib.pyplot as plt
import time

# === CONFIG ===
st.set_page_config(page_title="FleetLab Optimizer Demo", layout="wide")
st.title("🚌 FleetLab Routing & Cost Optimizer")

# === GOOGLE MAPS SETUP ===
gmaps = googlemaps.Client(key=st.secrets["google"]["maps_api_key"])

# === UPLOAD OR SIMULATE STOPS ===
st.sidebar.header("1. Load Stops")
option = st.sidebar.radio("Select input mode:", ["Upload CSV", "Simulate from School Name"])

if option == "Upload CSV":
    uploaded_file = st.sidebar.file_uploader("Upload stop CSV", type="csv")
    if uploaded_file:
        df_stops = pd.read_csv(uploaded_file)
    else:
        df_stops = pd.read_csv("sample_stops.csv")
else:
    school_name = st.sidebar.text_input("Enter School Name", "Northville High School, MI")
    if st.sidebar.button("Simulate Stops"):
        geo = gmaps.geocode(school_name)
        loc = geo[0]['geometry']['location']
        lat, lon = loc['lat'], loc['lng']
        # Generate mock stops near school
        df_stops = pd.DataFrame({
            "Stop Name": [f"Stop {i+1}" for i in range(30)],
            "lat": [lat + 0.01 * i / 30 for i in range(30)],
            "lon": [lon - 0.01 * i / 30 for i in range(30)],
            "Address": [school_name]*30
        })
    else:
        st.stop()

# === SAFETY SCORE SIMULATION ===
def calculate_ses(row):
    return 0.8 - 0.01 * int(row.name)  # mock SES score

df_stops["SES Score"] = df_stops.apply(calculate_ses, axis=1)
df_stops["Safety Rating"] = df_stops["SES Score"].apply(lambda s: "Safe" if s >= 0.7 else "Acceptable" if s >= 0.5 else "Unsafe")

# === SHOW MAP ===
st.subheader("📍 Stop Safety Map")
if "lat" in df_stops.columns and "lon" in df_stops.columns:
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
            popup=f"{row['Stop Name']}: {row['Safety Rating']}"
        ).add_to(cluster)
    st_folium(m, width=800)

# === FLEET MIX OPTIMIZATION ===
st.subheader("🚐 Fleet Mix Optimizer")
if st.button("Optimize Fleet Mix"):
    total_stops = len(df_stops)
    bus_capacity = 20
    van_capacity = 7
    best_mix = None
    lowest_cost = float('inf')

    for buses in range(0, 4):
        for vans in range(1, 7):
            if buses * bus_capacity + vans * van_capacity >= total_stops:
                cost = buses * 200 + vans * 120  # daily cost
                if cost < lowest_cost:
                    lowest_cost = cost
                    best_mix = (buses, vans)

    if best_mix:
        buses, vans = best_mix
        st.success(f"✅ Recommended Fleet: {buses} Buses and {vans} Vans")
        st.markdown(f"**Estimated Daily Cost:** ${lowest_cost:.2f}")
        st.markdown(f"**Driver Slots Needed:** {buses + vans}")
        st.markdown(f"**Total Stops Covered:** {total_stops}")
    else:
        st.error("❌ No valid fleet combination found.")

# === ROUTE COVERAGE SIMULATION ===
st.subheader("🧭 Route Coverage Summary")
if "SES Score" in df_stops:
    high_risk = df_stops[df_stops["Safety Rating"] == "Unsafe"].shape[0]
    med_risk = df_stops[df_stops["Safety Rating"] == "Acceptable"].shape[0]
    low_risk = df_stops[df_stops["Safety Rating"] == "Safe"].shape[0]
    st.write(f"🔴 Unsafe Stops: {high_risk}")
    st.write(f"🟠 Acceptable Stops: {med_risk}")
    st.write(f"🟢 Safe Stops: {low_risk}")

# === STOP TABLE ===
st.subheader("📋 Stop Table")
st.dataframe(df_stops, use_container_width=True)
