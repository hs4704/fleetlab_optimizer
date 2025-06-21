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

# === AUTO FILL MISSING FACTORS ===
def autofill_missing_fields(df):
    for idx, row in df.iterrows():
        address = row['Address']
        if 'Traffic Risk (T)' not in df.columns or pd.isna(row.get('Traffic Risk (T)')):
            df.at[idx, 'Traffic Risk (T)'] = 0.5
        if 'U-Turn Required (U)' not in df.columns or pd.isna(row.get('U-Turn Required (U)')):
            try:
                directions = gmaps.directions("school address", address, mode="driving")
                u_turn = 0
                for leg in directions:
                    for step in leg['legs'][0]['steps']:
                        if step.get('maneuver') in ['uturn-left', 'uturn-right']:
                            u_turn = 1
                df.at[idx, 'U-Turn Required (U)'] = u_turn
            except:
                df.at[idx, 'U-Turn Required (U)'] = 0
        if 'Construction Risk (C)' not in df.columns or pd.isna(row.get('Construction Risk (C)')):
            df.at[idx, 'Construction Risk (C)'] = 0.2
    return df

# === SELECT STOP INPUT METHOD ===
st.sidebar.header("1. Load Stops")
option = st.sidebar.radio("Select input mode:", ["Upload CSV", "Simulate from School Name"])
df_stops = None

if option == "Upload CSV":
    uploaded_file = st.sidebar.file_uploader("Upload stop CSV", type="csv")
    if uploaded_file:
        df_stops = pd.read_csv(uploaded_file)
        st.success("✅ File uploaded successfully!")
    else:
        try:
            df_stops = pd.read_csv("sample_stops.csv")
            st.warning("📄 Using default sample_stops.csv")
        except Exception as e:
            st.error(f"❌ Failed to load sample stops: {e}")
            st.stop()

elif option == "Simulate from School Name":
    from simulator import simulate_district
    school_name = st.sidebar.text_input("Enter School Name", "Northville High School, MI")
    if st.sidebar.button("Simulate Stops"):
        try:
            sim = simulate_district(school_name)
            stops = sim["stops"]
            df_stops = pd.DataFrame({
                "Stop Name": [f"Stop {i+1}" for i in range(len(stops))],
                "lat": [pt.y for pt in stops],
                "lon": [pt.x for pt in stops],
                "Address": [school_name] * len(stops)
            })
            st.success(f"✅ Simulated stops generated for: {school_name}")
        except Exception as e:
            st.error(f"❌ Simulation failed: {e}")
            st.stop()
    else:
        st.info("📍 Enter a school name and click 'Simulate Stops'")
        st.stop()

# === ENSURE LAT/LON AND SAFETY FACTORS EXIST ===
if "lat" not in df_stops.columns or "lon" not in df_stops.columns:
    if "Address" in df_stops.columns:
        lats, lons = geocode_addresses(df_stops["Address"])
        df_stops["lat"] = lats
        df_stops["lon"] = lons
    else:
        st.warning("📍 No Address column found, and no lat/lon available.")
        st.stop()

with st.spinner("Auto-generating missing safety factors..."):
    df_stops = autofill_missing_fields(df_stops)

# === SAFETY SCORE LOGIC ===
def calculate_ses(row):
    return 0.8 - 0.01 * int(row.name)  # mock SES scoring

df_stops["SES Score"] = df_stops.apply(calculate_ses, axis=1)
df_stops["Safety Rating"] = df_stops["SES Score"].apply(
    lambda s: "Safe" if s >= 0.7 else "Acceptable" if s >= 0.5 else "Unsafe"
)

# === MAP VIEW ===
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
else:
    st.warning("No lat/lon data available to display map.")

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

# === ROUTE COVERAGE STATS ===
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
