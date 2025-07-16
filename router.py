import numpy as np
import osmnx as ox
import networkx as nx
from sklearn.cluster import KMeans
from shapely.geometry import Point
import geopandas as gpd
import pandas as pd

def cluster_stops(df_stops, n_clusters=3):
    """
    Adds a 'cluster' column using KMeans on lat/lon.
    """
    coords = df_stops[["lat", "lon"]].values
    kmeans = KMeans(n_clusters=n_clusters, random_state=42).fit(coords)
    df_stops["cluster"] = kmeans.labels_
    return df_stops

def route_cluster(cluster_df, G, school_latlon):
    """
    Returns a TSP-based OSM route (list of node IDs) for one cluster.
    """
    school_node = ox.distance.nearest_nodes(G, school_latlon[1], school_latlon[0])
    stop_nodes = [
        ox.distance.nearest_nodes(G, row["lon"], row["lat"])
        for _, row in cluster_df.iterrows()
    ]
    all_nodes = [school_node] + stop_nodes

    tsp_graph = nx.complete_graph(len(all_nodes))
    for i in tsp_graph.nodes:
        for j in tsp_graph.nodes:
            if i != j:
                try:
                    length = nx.shortest_path_length(G, all_nodes[i], all_nodes[j], weight="length")
                    tsp_graph[i][j]["weight"] = length
                except:
                    tsp_graph[i][j]["weight"] = float("inf")

    tsp_cycle = nx.approximation.traveling_salesman_problem(tsp_graph, cycle=True)
    ordered_osmids = [all_nodes[i] for i in tsp_cycle]
    return ordered_osmids

def cluster_and_route_stops(df_stops, school_coords, n_clusters=3):
    """
    Clusters stops, builds road graph, and returns routes for each cluster.
    """
    df_stops = cluster_stops(df_stops, n_clusters=n_clusters)
    G = ox.graph_from_point(school_coords, dist=3000, network_type="drive")

    # Add nearest OSM node to each stop
    df_stops["osmid"] = df_stops.apply(lambda row: ox.distance.nearest_nodes(G, row["lon"], row["lat"]), axis=1)
    school_node = ox.distance.nearest_nodes(G, school_coords[1], school_coords[0])

    routes = {}
    for cid in sorted(df_stops["cluster"].unique()):
        cluster_df = df_stops[df_stops["cluster"] == cid]
        stop_nodes = list(cluster_df["osmid"])
        all_nodes = [school_node] + stop_nodes

        tsp_graph = nx.complete_graph(len(all_nodes))
        for i in tsp_graph.nodes:
            for j in tsp_graph.nodes:
                if i != j:
                    try:
                        length = nx.shortest_path_length(G, all_nodes[i], all_nodes[j], weight="length")
                        tsp_graph[i][j]["weight"] = length
                    except:
                        tsp_graph[i][j]["weight"] = float("inf")

        tsp_cycle = nx.approximation.traveling_salesman_problem(tsp_graph, cycle=True)
        ordered_osmids = [all_nodes[i] for i in tsp_cycle]
        routes[cid] = ordered_osmids

    return routes, G, df_stops

def export_routes_geojson(routes, G):
    """
    Converts TSP routes into a GeoJSON feature collection.
    """
    features = []
    for rid, path in routes.items():
        for u, v in zip(path[:-1], path[1:]):
            try:
                segment = nx.shortest_path(G, u, v, weight="length")
                line = ox.utils_graph.graph_to_gdfs(G.subgraph(segment), nodes=False).geometry.union_all()
                features.append({
                    "type": "Feature",
                    "geometry": line.__geo_interface__,
                    "properties": {"route": int(rid)}
                })
            except Exception:
                continue
    return {
        "type": "FeatureCollection",
        "features": features
    }

__all__ = ["cluster_and_route_stops", "export_routes_geojson"]
