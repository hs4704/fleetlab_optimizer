import streamlit as st
import pandas as pd
import geopandas as gpd
from geo_utils import geocode_school_address, get_district_geometry, generate_weighted_stops

# === PAGE CONFIG ===
st.set_page_config(page_title="FleetLab Optimizer", layout="wide")
st.title("🚍 FleetLab Transportation Optimization Prototype")

# === USER INPUT ===
st.header("Step 1: Input Your School or Address")
school_input = st.text_input("Enter your school name or address:", "Northville High School")

# === PROCESS ===
if st.button("Find District and Generate Stops"):
    with st.spinner("Locating school and generating stops..."):
        try:
            # 1. Geocode school
            lat, lon = geocode_school_address(school_input)
            st.success(f"📍 School located at ({lat:.5f}, {lon:.5f})")

            # 2. Match district boundary
            district_poly, district_name, district_code = get_district_geometry(lat, lon)
            st.info(f"✅ Detected district: {district_name} (Code: {district_code})")

            # 3. Generate sample stops
            stops_df = generate_weighted_stops(district_poly, (lat, lon), n=50)

            # 4. Map Visualization
            import folium
            from streamlit_folium import st_folium

            m = folium.Map(location=[lat, lon], zoom_start=13, tiles="CartoDB positron")
            folium.Marker([lat, lon], popup="School Location", icon=folium.Icon(color='red')).add_to(m)

            for _, row in stops_df.iterrows():
                folium.CircleMarker(
                    location=[row['lat'], row['lon']],
                    radius=4,
                    color='blue',
                    fill=True,
                    fill_opacity=0.8,
                    popup=f"Stop: ({row['lat']:.5f}, {row['lon']:.5f})"
                ).add_to(m)

            st_folium(m, width=900, height=600)

            st.subheader("Generated Stop Data")
            st.dataframe(stops_df)

        except Exception as e:
            st.error(f"❌ An error occurred: {e}")
