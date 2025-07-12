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
from router import solve_routes

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
        df_uploaded.columns = df_uploaded.columns.str.strip().str.lower()  # Normalize

        st.warning(f"📋 Columns in uploaded file: {list(df_uploaded.columns)}")

        # Try converting Excel-style address sheet
        if "home address" in df_uploaded.columns and "city" in df_uploaded.columns:
            
            df_stops = preprocess_excel_style_sheet(df_uploaded)
            

            # Normalize 'school' column
            if "school" not in df_stops.columns:
                st.error("❌ 'School' column not found after processing. Please check the format.")
                st.stop()

            df_stops["school"] = df_stops["school"].astype(str).str.strip()
            schools = sorted(df_stops["school"].dropna().unique())

            if not schools:
                st.error("❌ No schools found in uploaded sheet.")
                st.stop()

            selected_school = st.sidebar.selectbox("Select a school to process", schools)
            df_stops = df_stops[df_stops["school"] == selected_school].copy()

            # Try to geocode school for routing reference
            try:
                school_geocode = gmaps.geocode(selected_school)
                if school_geocode:
                    loc = school_geocode[0]["geometry"]["location"]
                    st.session_state["school_coords"] = (loc["lat"], loc["lng"])
                else:
                    st.warning("⚠️ Could not geocode selected school. Routes may not generate correctly.")
            except Exception as e:
                st.warning(f"⚠️ Geocoding error for school: {e}")

            st.success(f"✅ Now processing {len(df_stops)} stops for: {selected_school}")

        else:
            # Handle already formatted stop data
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
            st.error("❌Please enter a school name before simulating.")
            st.stop()
        try:
            df_stops = generate_stops_for_school(school, n=n_stops)
            if df_stops.empty:
                st.error("❌ Simulation returned no stops.")
                st.stop()
            st.success(f"✅ Simulated {len(df_stops)} stops for: {school}")
            st.dataframe(df_stops.head())

            # Save simulated stops
            st.session_state["df_stops"] = df_stops

            # Store school coordinates for routing
            school_lat = df_stops["lat"].mean()
            school_lon = df_stops["lon"].mean()
            st.session_state["school_coords"] = (school_lat, school_lon)

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
    if "Address" in df_stops.columns:
        addresses = df_stops["Address"].fillna("").astype(str).tolist()
        lats, lons = geocode_addresses(addresses)

        if len(lats) != len(df_stops):
            st.error(f"❌ Geocoding failed: expected {len(df_stops)} coords but got {len(lats)}.")
            st.stop()

        df_stops = df_stops.copy()
        df_stops["lat"] = pd.Series(lats, index=df_stops.index)
        df_stops["lon"] = pd.Series(lons, index=df_stops.index)
    else:
        st.error("❌ No lat/lon or Address available for geocoding.")
        st.stop()

# === STEP 3: Drop invalid coords (prevents map crash) ===
df_stops = df_stops.dropna(subset=["lat", "lon"])
df_stops = df_stops[df_stops["lat"].apply(lambda x: isinstance(x, (float, int)))]

# === STEP 4: Safety Scoring ===
with st.spinner("🔍 Estimating safety scores..."):
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
            popup=f"{row.get('Stop Name', 'Stop')}: {row['Safety Rating']}"
        ).add_to(cluster)
    st_folium(m, width=900)
except Exception as e:
    st.error(f"❌ Map rendering failed: {e}")

# === OPTIMIZE FLEET MIX ===
st.subheader("🚐 Fleet Mix Optimizer")
bus_capacity = 55
van_capacity = 9
bus_cost = 483  
van_cost = 95 + 8.33 + 16.31 #Total 199.64
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
        buses, vans, drivers = best_mix
        st.success(f"✅ Optimal Fleet: {buses} Buses, {vans} Vans")
        st.markdown(f"- **Drivers Needed:** {drivers}")
        st.markdown(f"- **Estimated Daily Cost:** `${lowest_cost:,.2f}`")
        st.markdown(f"- **Total Capacity:** {buses * bus_capacity + vans * van_capacity}")
    else:
        st.error("❌ No valid fleet mix found.")
# === ROUTE GENERATION ===
st.subheader("🗺️ Route Planner")

if st.button("Generate Routes"):
    with st.spinner("🧭 Solving routes with OR-Tools..."):
        try:
            if "school_coords" not in st.session_state:
                st.warning("⚠️ School location not available. Cannot generate routes.")
            else:
                depot = st.session_state["school_coords"]
                stop_coords = [(row["lat"], row["lon"]) for _, row in df_stops.iterrows()]
                all_locations = [depot] + stop_coords

                from router import solve_routes  # safe to import here
                routes = solve_routes(all_locations, num_vehicles=4, depot_index=0)

                if not routes:
                    st.error("❌ Route optimization failed. Try fewer stops or vehicles.")
                else:
                    st.session_state["routes"] = routes
                    st.session_state["all_locations"] = all_locations
                    st.success(f"✅ Generated {len(routes)} routes from school!")

        except Exception as e:
            st.error(f"❌ Route generation failed: {e}")

# === DISPLAY ROUTES IF PRESENT ===
if "routes" in st.session_state and "all_locations" in st.session_state:
    st.subheader("📍 Optimized Route Map")
    depot = st.session_state["school_coords"]
    all_locations = st.session_state["all_locations"]
    routes = st.session_state["routes"]

    m = folium.Map(location=depot, zoom_start=12)
    colors = ["red", "blue", "green", "purple", "orange", "darkred", "lightblue", "gray"]
    for i, route in enumerate(routes):
        color = colors[i % len(colors)]
        points = [all_locations[idx] for idx in route]
        folium.PolyLine(points, color=color, weight=4, opacity=0.8).add_to(m)
        for j, pt in enumerate(points):
            folium.CircleMarker(
                location=pt,
                radius=4,
                color=color,
                fill=True,
                fill_opacity=0.8,
                popup=f"Route {i+1} Stop {j}" if j > 0 else f"Depot"
            ).add_to(m)

    st_folium(m, width=900)
# === SUMMARY ===
st.subheader("🧭 Route Coverage Summary")
st.write(f"🔴 Unsafe Stops: {df_stops[df_stops['Safety Rating']=='Unsafe'].shape[0]}")
st.write(f"🟠 Acceptable Stops: {df_stops[df_stops['Safety Rating']=='Acceptable'].shape[0]}")
st.write(f"🟢 Safe Stops: {df_stops[df_stops['Safety Rating']=='Safe'].shape[0]}")

# === DATA TABLE ===
st.subheader("📋 Stop Table")
st.dataframe(df_stops, use_container_width=True)
