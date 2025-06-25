#app.py
import streamlit as st
import pandas as pd
import googlemaps
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
import time
from simulator import generate_stops_for_school
from utils import autofill_missing_fields, calculate_ses

# === CONFIG ===
st.set_page_config(page_title="FleetLab Optimizer Demo", layout="wide")
st.title("🚌 FleetLab Routing & Cost Optimizer")

# === GOOGLE MAPS CLIENT ===
gmaps = googlemaps.Client(key=st.secrets["google"]["maps_api_key"])

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

# === SIDEBAR STOP LOADING ===
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
    num_stops = st.sidebar.slider("Number of stops", 10, 100, 50)

    if "simulated_df" not in st.session_state:
        st.session_state.simulated_df = None

    if st.sidebar.button("Simulate Stops"):
        try:
            df_stops = generate_stops_for_school(school, n=num_stops)
            if df_stops is None or df_stops.empty or "lat" not in df_stops.columns:
                raise ValueError("Simulation returned no usable stop data.")
            st.session_state.simulated_df = df_stops
            st.success(f"✅ Simulated {len(df_stops)} stops for: {school}")
        except Exception as e:
            st.error(f"❌ Simulation failed: {e}")
            st.stop()
    elif st.session_state.simulated_df is not None:
        df_stops = st.session_state.simulated_df
    else:
        st.info("📍 Enter a school and click simulate.")
        st.stop()

# === GEOCODE FALLBACK ===
if "lat" not in df_stops.columns or "lon" not in df_stops.columns:
    if "Address" in df_stops.columns:
        lats, lons = geocode_addresses(df_stops["Address"])
        df_stops["lat"] = lats
        df_stops["lon"] = lons
    else:
        st.error("❌ Missing location data.")
        st.stop()

# === SAFETY SCORING ===
with st.spinner("🔍 Processing stop safety..."):
    df_stops = autofill_missing_fields(df_stops)
    df_stops["SES Score"] = df_stops.apply(calculate_ses, axis=1)
    df_stops["Safety Rating"] = df_stops["SES Score"].apply(
        lambda s: "Safe" if s >= 0.7 else "Acceptable" if s >= 0.5 else "Unsafe"
    )

# === STOP MAP ===
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
    st.error(f"❌ Failed to render map: {e}")

# === STOP TABLE ===
st.subheader("📋 Stop Table")
st.dataframe(df_stops, use_container_width=True)

