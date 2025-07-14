#router.py 

import pandas as pd
import numpy as np
import osmnx as ox
import networkx as nx
from sklearn.cluster import KMeans
from shapely.geometry import Point

def cluster_stops(df_stops, n_clusters=3):
    coords = df_stops[['lat', 'lon']].to_numpy()
    kmeans = KMeans(n_clusters=n_clusters, random_state=42).fit(coords)
    df_stops['cluster'] = kmeans.labels_
    return df_stops

def solve_routes_osmnx(df_stops, school_coords):
    G = ox.graph_from_point(school_coords, dist=10000, network_type='drive')
    df_stops['osmid'] = df_stops.apply(lambda row: ox.distance.nearest_nodes(G, row['lon'], row['lat']), axis=1)
    school_node = ox.distance.nearest_nodes(G, school_coords[1], school_coords[0])

    routes = {}
    for cluster_id in sorted(df_stops['cluster'].unique()):
        group = df_stops[df_stops['cluster'] == cluster_id]
        node_list = [school_node] + group['osmid'].tolist() + [school_node]

        full_path = []
        for i in range(len(node_list) - 1):
            try:
                path = nx.shortest_path(G, node_list[i], node_list[i + 1], weight='length')
                full_path += path[:-1]  # avoid duplicating nodes
            except:
                continue
        full_path.append(node_list[-1])
        routes[cluster_id] = full_path

    return G, routes

def export_route_paths(G, routes, output_path='routes.geojson'):
    all_features = []
    for cid, path in routes.items():
        if len(path) < 2:
            continue
        coords = [(G.nodes[n]['y'], G.nodes[n]['x']) for n in path]
        line = {'type': 'Feature', 'geometry': {'type': 'LineString', 'coordinates': [(x, y) for y, x in coords]},
                'properties': {'cluster': int(cid)}}
        all_features.append(line)
    geojson = {'type': 'FeatureCollection', 'features': all_features}
    import json
    with open(output_path, 'w') as f:
        json.dump(geojson, f)
    return output_path
