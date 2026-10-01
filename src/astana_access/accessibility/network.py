import json

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy.sparse import coo_matrix, csr_matrix
from scipy.sparse.csgraph import connected_components, dijkstra
from scipy.spatial import cKDTree

from astana_access.config import CRS_GEO, CRS_METRIC, PROCESSED, RAW, settings
from astana_access.ingest.http import post_json
from astana_access.ingest.osm import CITY_RELATION

EXCLUDED = (
    "motorway|motorway_link|construction|proposed|raceway|bus_guideway|escape|abandoned|"
    "platform|corridor|elevator|razed|disused"
)
QUERY = f"""
[out:json][timeout:600];
rel({CITY_RELATION});
map_to_area -> .city;
way(area.city)[highway][highway!~"^({EXCLUDED})$"][foot!~"^(no|private)$"][area!~"^yes$"];
out body;
>;
out skel qt;
"""
WALK_SPEED_M_PER_MIN = 75.0
CACHE = RAW / "osm" / "walk_network.json"


def fetch(force: bool = False) -> dict:
    if CACHE.exists() and not force:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    payload = post_json(settings.overpass_url, {"data": QUERY})
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def build_tables(payload: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    nodes = {
        element["id"]: (element["lon"], element["lat"])
        for element in payload["elements"]
        if element["type"] == "node"
    }
    pairs = []
    for element in payload["elements"]:
        if element["type"] != "way":
            continue
        refs = [ref for ref in element["nodes"] if ref in nodes]
        highway = element.get("tags", {}).get("highway", "")
        pairs.extend((a, b, highway) for a, b in zip(refs, refs[1:], strict=False) if a != b)
    node_frame = pd.DataFrame(
        [(key, lon, lat) for key, (lon, lat) in nodes.items()], columns=["osm_id", "lon", "lat"]
    )
    transformer = Transformer.from_crs(CRS_GEO, CRS_METRIC, always_xy=True)
    node_frame["x"], node_frame["y"] = transformer.transform(
        node_frame["lon"].to_numpy(), node_frame["lat"].to_numpy()
    )
    edges = pd.DataFrame(pairs, columns=["u", "v", "highway"])
    position = pd.Series(np.arange(len(node_frame)), index=node_frame["osm_id"])
    edges["i"] = position[edges["u"]].to_numpy()
    edges["j"] = position[edges["v"]].to_numpy()
    xy = node_frame[["x", "y"]].to_numpy()
    edges["length_m"] = np.hypot(*(xy[edges["i"]] - xy[edges["j"]]).T)
    return node_frame, edges


class WalkNetwork:
    def __init__(self, nodes: pd.DataFrame, edges: pd.DataFrame) -> None:
        size = len(nodes)
        matrix = coo_matrix(
            (
                np.concatenate([edges["length_m"], edges["length_m"]]),
                (
                    np.concatenate([edges["i"], edges["j"]]),
                    np.concatenate([edges["j"], edges["i"]]),
                ),
            ),
            shape=(size, size),
        ).tocsr()
        _, labels = connected_components(matrix, directed=False)
        largest = np.bincount(labels).argmax()
        keep = np.flatnonzero(labels == largest)
        remap = np.full(size, -1)
        remap[keep] = np.arange(len(keep))
        sub = matrix[keep][:, keep]
        self.graph: csr_matrix = sub
        self.nodes = nodes.iloc[keep].reset_index(drop=True)
        self.tree = cKDTree(self.nodes[["x", "y"]].to_numpy())
        self.share_of_nodes_kept = float(len(keep) / size)

    def snap(self, x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        distance, index = self.tree.query(np.column_stack([x, y]))
        return index, distance

    def distances(self, sources: np.ndarray, limit_m: float) -> np.ndarray:
        unique, inverse = np.unique(sources, return_inverse=True)
        result = dijkstra(self.graph, directed=False, indices=unique, limit=limit_m)
        return result[inverse]


def load() -> WalkNetwork:
    nodes_path = PROCESSED / "walk_nodes.parquet"
    edges_path = PROCESSED / "walk_edges.parquet"
    if nodes_path.exists() and edges_path.exists():
        nodes, edges = pd.read_parquet(nodes_path), pd.read_parquet(edges_path)
    else:
        nodes, edges = build_tables(fetch())
        nodes.to_parquet(nodes_path)
        edges.to_parquet(edges_path)
    return WalkNetwork(nodes, edges)


def edges_geometry(network: WalkNetwork, edges: pd.DataFrame) -> gpd.GeoDataFrame:
    from shapely.geometry import LineString

    xy = network.nodes[["x", "y"]].to_numpy()
    lines = [LineString([xy[i], xy[j]]) for i, j in zip(edges["i"], edges["j"], strict=True)]
    return gpd.GeoDataFrame(edges, geometry=lines, crs=CRS_METRIC)
