#===Builds the stop layout and simulates the school district zone===

import geopandas as gpd
import pandas as pd
from shapely.ops import transform
from shapely.geometry import Point
from utils import geocode_address, get_district_geometry, generate_stops

def simulate_district(school_name, student_df=None):
    school_latlon = geocode_address(school_name)
    district_polygon, utm_crs = get_district_geometry(school_latlon)
    school_point = Point(school_latlon[::-1])  # (lon, lat)

    if student_df is None:
        stops = generate_stops(district_polygon, school_point, utm_crs)
    else:
        # TODO: Add geocoding + clustering real addresses later
        stops = generate_stops(district_polygon, school_point, utm_crs)

    return {
        "school": school_point,
        "district": district_polygon,
        "stops": stops,
        "utm_crs": utm_crs
    }
def generate_stops_for_school(school_name):
    """Public interface to generate a DataFrame of stops for a given school name."""
    sim = simulate_district(school_name)
    stops = sim["stops"]
    
    # Ensure it's a GeoDataFrame and convert geometry to lat/lon
    if not isinstance(stops, gpd.GeoDataFrame):
        raise ValueError("stops is not a GeoDataFrame.")

    stops = stops.to_crs(epsg=4326)  # WGS84 lat/lon
    stops["lat"] = stops.geometry.y
    stops["lon"] = stops.geometry.x
    stops["Stop Name"] = [f"Simulated Stop {i+1}" for i in range(len(stops))]
    stops["Address"] = school_name

    return stops[["Stop Name", "lat", "lon", "Address"]]
