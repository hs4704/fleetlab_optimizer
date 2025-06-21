#=== Runs cost +performance optimization, creates an interactive map, and summarizes the proposal


from cost_model import CostModel
from fleet_optimizer import FleetOptimizer
import folium
from shapely.ops import transform
import pyproj

def generate_proposal(sim):
    cost_model = CostModel()
    optimizer = FleetOptimizer(
        num_students=len(sim["stops"]),
        num_vans=5,
        num_buses=2,
        cost_model=cost_model
    )

    result = optimizer.estimate_cost(miles_per_trip=20, hours_per_trip=1)

    # Map rendering
    project_back = pyproj.Transformer.from_crs(sim["utm_crs"], "EPSG:4326", always_xy=True).transform
    stops_latlon = [transform(project_back, pt) for pt in sim["stops"]]

    m = folium.Map(location=[sim["school"].y, sim["school"].x], zoom_start=12)
    folium.Marker(location=[sim["school"].y, sim["school"].x], popup="School").add_to(m)
    for pt in stops_latlon:
        folium.CircleMarker(location=[pt.y, pt.x], radius=4, color='blue', fill=True).add_to(m)

    return {
        "fleet_mix": result,
        "summary": {
            "Total Cost": f"${result['total_cost']:.2f}",
            "Drivers Needed": result["assigned_vans"] + result["assigned_buses"]
        },
        "map_html": m._repr_html_()
    }
