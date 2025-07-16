# 🚌 FleetLab Safety & Routing Dashboard

**FleetLab** is an interactive geospatial simulation and optimization tool for improving school transportation systems. Built in Python with Streamlit, this dashboard helps school districts design safer, more efficient bus and van routes by simulating realistic student stops, scoring safety at each stop, and recommending optimal fleet mixes.

---

## 🔍 Project Overview

School transportation logistics require balancing **student safety**, **vehicle efficiency**, and **cost-effectiveness**. FleetLab tackles this challenge by:

- Simulating student stop locations using real road/building data
- Scoring each stop using a custom Safety Evaluation Score (SES)
- Visualizing high-risk vs. safe stops on interactive maps
- Recommending the ideal mix of buses and vans for each school
- Providing route clustering and visual previews using OSM-based networks

---

## 🎯 Features

| Feature                        | Description |
|-------------------------------|-------------|
| 🏫 **Stop Simulation**         | Generates bus stop locations from a school address or uploaded student data using OpenStreetMap and Google Maps. |
| 🚦 **Safety Scoring (SES)**    | Evaluates stop safety based on visibility, lighting, traffic exposure, road type, U-turns, and construction risk. |
| 🗺️ **Interactive Mapping**     | Visualizes stops using `folium`, color-coded by safety (Red: Unsafe, Orange: Acceptable, Green: Safe). |
| 🚐 **Fleet Mix Optimization**  | Determines the most cost-effective combination of buses and vans based on capacity, route coverage, and driver costs. |
| 🧭 **OSM-Based Route Clustering** | Clusters stops and simulates routing using OpenStreetMap roads and shortest-path logic. |
| 📥 **Flexible Data Input**     | Accepts CSV uploads or generates data via a school name/address. |
| 📤 **Export Tools**            | Allows download of route paths and stop data as CSV or GeoJSON for reporting or integration. |

---

## 🛠️ Technologies Used

- **Python** (Pandas, NumPy, Scikit-learn)
- **Streamlit** – interactive web app
- **Folium** – geospatial map rendering
- **Google Maps API** – geocoding, distance matrices, U-turn detection
- **OSMnx** / **NetworkX** – OpenStreetMap road network and routing
- **KMeans** – stop clustering and route grouping
- **GeoJSON & CSV Export** – for easy download and reporting

---

## 🧪 How It Works

1. **Input**  
   - Upload a CSV with student addresses and school info  
   - Or enter a school name to simulate stops for that district  

2. **Stop Generation**  
   - Uses building centroids and population density from OSM to sample stops  

3. **SES Scoring**  
   - Each stop is scored based on:
     - Nearby traffic risk
     - Road type
     - Visibility and lighting proxies
     - U-turn hazards from Google Directions
     - Construction presence (mocked or real)

4. **Routing & Optimization**  
   - Stops are clustered by proximity and road connectivity  
   - Routes are simulated between stops using shortest paths on OSM roads  
   - Optimal fleet mix is calculated based on vehicle capacities and costs  

5. **Output**  
   - Interactive safety map  
   - Recommended fleet mix  
   - Route visualizations  
   - Downloadable stop/route files  
