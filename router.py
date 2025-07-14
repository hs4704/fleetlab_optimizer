# router.py

import numpy as np
import osmnx as ox
import networkx as nx
from sklearn.cluster import KMeans
from shapely.geometry import Point
import geopandas as gpd

def cluster_stops(df_stops, n_clusters=3):
    coords = df_stops[["lat", "lon"]].values
    kmeans = KMeans(n_clusters=n_clusters, random_state=42).fit(coords)
    df_stops["cluster"] = kmeans.labels_
    return df_stops

def route_cluster(cluster_df, G, school_latlon):
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
    df_clustered = cluster_stops(df_stops.copy(), n_clusters)
    G = ox.graph_from_point(school_coords, dist=3000, network_type="drive")
    routes = {}

    for cid in sorted(df_clustered["cluster"].unique()):
        group = df_clustered[df_clustered["cluster"] == cid]
        route_nodes = route_cluster(group, G, school_coords)
        routes[cid] = route_nodes

    return routes, G, df_clustered

def export_routes_geojson(routes, G):
    features = []
    for rid, path in routes.items():
        for u, v in zip(path[:-1], path[1:]):
            try:
                segment = nx.shortest_path(G, u, v, weight="length")
                line = ox.utils_graph.graph_to_gdfs(G.subgraph(segment), nodes=False).geometry.unary_union
                features.append({
                    "type": "Feature",
                    "geometry": line.__geo_interface__,
                    "properties": {"route": int(rid)}
                })
            except:
                continue
    return {
        "type": "FeatureCollection",
        "features": features
    }

__all__ = ["cluster_and_route_stops", "export_routes_geojson"]
