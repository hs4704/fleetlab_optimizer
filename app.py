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
import osmnx as ox


def simple_route_solver(school_coords, stop_coords, n_routes=3):
    from sklearn.cluster import KMeans

    if len(stop_coords) < n_routes:
        n_routes = max(1, len(stop_coords))

    kmeans = KMeans(n_clusters=n_routes, random_state=42).fit(stop_coords)
    labels = kmeans.labels_

    routes = []
    for i in range(n_routes):
        cluster = [pt for idx, pt in enumerate(stop_coords) if labels[idx] == i]
        # sort by distance from school
        cluster.sort(key=lambda pt: (pt[0] - school_coords[0])**2 + (pt[1] - school_coords[1])**2)
        # ensure school is first and last
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
st.write("📍 School coords:", st.session_state.get("school_coords"))
st.write("📍 First few stop coords:", list(zip(df_stops['lat'], df_stops['lon']))[:3])
# === ROUTE GENERATION ===
st.subheader("🗺️ Route Planner")
if st.button("Generate Routes"):
    try:
        school_coords = st.session_state.get("school_coords")
        if not school_coords:
            st.error("⚠️ No school location available.")
        else:
            with st.spinner("🚐 Routing on real roads..."):
                from router import cluster_and_route_stops
                routes, G, clustered_df = cluster_and_route_stops(df_stops.copy(), school_coords, n_clusters=3)
                st.session_state["routes"] = routes
                st.session_state["G"] = G
                st.session_state["clustered_df"] = clustered_df
                st.success(f"✅ Generated {len(routes)} OSM-based routes.")
    except Exception as e:
        st.error(f"❌ Routing error: {e}")

# === DISPLAY ROUTES ===
if "routes" in st.session_state and "G" in st.session_state:
    st.subheader("📍 Optimized OSM-Based Route Map")
    routes = st.session_state["routes"]
    G = st.session_state["G"]
    clustered_df = st.session_state.get("clustered_df")

    if clustered_df is None:
        st.warning("No clustered stop data available. Please run routing first.")
    else:
        depot = st.session_state["school_coords"]
        school_node = ox.distance.nearest_nodes(G, depot[1], depot[0])
        m = folium.Map(location=depot, zoom_start=13)
        colors = ["red", "blue", "green", "purple", "orange", "darkred"]

        for cid, route_nodes in routes.items():
            full_path = []
            for u, v in zip(route_nodes[:-1], route_nodes[1:]):
                try:
                    segment = nx.shortest_path(G, u, v, weight='length')
                    full_path += segment[:-1]
                except:
                    continue
            full_path.append(route_nodes[-1])

            try:
                edge_gdf = ox.graph_to_gdfs(G.subgraph(full_path), nodes=False)
                line = edge_gdf.geometry.unary_union

                if isinstance(line, LineString):
                    folium.PolyLine(list(line.coords), color=colors[cid % len(colors)], weight=5).add_to(m)
                elif isinstance(line, MultiLineString):
                    for segment in line.geoms:
                        folium.PolyLine(list(segment.coords), color=colors[cid % len(colors)], weight=5).add_to(m)
            except:
                st.warning(f"Route {cid} plotting failed.")

        st_folium(m, width=950, height=600)
# === OPTIMIZE FLEET MIX ===
st.subheader("🚐 Fleet Mix Optimizer")
bus_capacity = 55
van_capacity = 9
bus_cost = 483  
van_cost = 95 + 8.33 + 16.31  # Total: 199.64
driver_cost = 80

if st.button("Optimize Fleet Mix"):
    total_stops = len(df_stops)
    best_mix = None
    lowest_cost = float("inf")

    for buses in range(0, 7):  # includes 0 buses
        for vans in range(0, 11):  # includes 0 vans
            capacity = buses * bus_capacity + vans * van_capacity
            if capacity >= total_stops:
                drivers = buses + vans
                cost = (buses * bus_cost) + (vans * van_cost) + (drivers * driver_cost)
                if cost < lowest_cost:
                    lowest_cost = cost
                    best_mix = {
                        "buses": buses,
                        "vans": vans,
                        "drivers": drivers,
                        "cost": cost,
                        "capacity": capacity
                    }

    if best_mix:
        st.session_state["fleet_mix"] = best_mix
    else:
        st.error("No valid fleet mix found.")

# === DISPLAY FLEET MIX RESULTS ===
if "fleet_mix" in st.session_state:
    mix = st.session_state["fleet_mix"]
    st.success(f"✅ Optimal Fleet: {mix['buses']} Buses, {mix['vans']} Vans")
    st.markdown(f"- **Drivers Needed:** {mix['drivers']}")
    st.markdown(f"- **Estimated Daily Cost:** ${mix['cost']:,.2f}")
    st.markdown(f"- **Total Capacity:** {mix['capacity']}")

# === EXECUTIVE SUMMARY ===
st.subheader("📊 Executive Summary")
total_stops = len(df_stops)
buses_needed = int(np.ceil(total_stops / bus_capacity))
baseline_cost = (buses_needed * bus_cost) + (buses_needed * driver_cost)

if "fleet_mix" in st.session_state:
    optimized = st.session_state["fleet_mix"]
    savings = baseline_cost - optimized["cost"]
    safe_count = df_stops[df_stops["Safety Rating"] == "Safe"].shape[0]
    safe_pct = round(100 * safe_count / total_stops, 1)
    
    st.markdown(f"""
    ### ✅ FleetLab Optimization:
    - **Recommended Fleet**: {optimized['buses']} Buses, {optimized['vans']} Vans  
    - **Drivers Needed**: {optimized['drivers']}  
    - **Optimized Cost**: ${optimized['cost']:,.2f}  
    - **Baseline (All Buses)**: ${baseline_cost:,.2f}  
    - **Daily Savings**: ${savings:,.2f}  
    - **% of Safe Stops**: {safe_pct}%  
    """)
else:
    st.info("ℹ️ Run the optimizer to compare cost and safety improvements.")

# === FINAL STOP TABLE ===
st.subheader("📋 Final Stop Table")
st.dataframe(df_stops, use_container_width=True)
