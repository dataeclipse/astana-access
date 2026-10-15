import json

import geopandas as gpd
import h3
import numpy as np
import pandas as pd

from astana_access.accessibility.coverage import facilities, origin_destination
from astana_access.accessibility.e2sfca import load_inputs, supply_measures
from astana_access.accessibility.network import load
from astana_access.config import CRS_GEO, CRS_METRIC, PROCESSED, RAW, REPORTS, ROOT
from astana_access.ingest import school_register
from astana_access.ingest.preschool_capacity import attendance_by_id
from astana_access.optimization.backtest import covered, official_programme
from astana_access.population.model import OFFICIAL_2026

OUT = ROOT / "dashboard" / "data"
RADII_M = (1000, 1500)
ROAD_CLASSES = {"motorway", "trunk", "primary", "secondary"}
DIGITS = 5
DEMAND = {"school": "school_station", "preschool": "preschool_station"}


def rounded(value):
    if isinstance(value, float):
        return round(value, DIGITS)
    if isinstance(value, (list, tuple)):
        return [rounded(v) for v in value]
    return value


def geojson(frame: gpd.GeoDataFrame, columns: list[str]) -> dict:
    data = json.loads(frame[[*columns, "geometry"]].to_crs(CRS_GEO).to_json(drop_id=True))
    for feature in data["features"]:
        feature["geometry"]["coordinates"] = rounded(feature["geometry"]["coordinates"])
    return data


def number(value) -> float | None:
    return None if value is None or pd.isna(value) else float(value)


def write(name: str, payload) -> int:
    path = OUT / name
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=number)
    path.write_text(text, encoding="utf-8")
    return len(text)


def base_layers() -> dict:
    districts = gpd.read_file(PROCESSED / "districts.gpkg", layer="districts").to_crs(CRS_METRIC)
    districts["geometry"] = districts.simplify(40)
    lines = gpd.read_file(RAW / "osm" / "lines.gpkg").to_crs(CRS_METRIC)
    roads = lines[(lines["kind"] == "highway") & lines["class"].isin(ROAD_CLASSES)].copy()
    roads["type"] = np.where(
        roads["class"].isin({"motorway", "trunk", "primary"}), "major", "minor"
    )
    river = lines[(lines["kind"] == "waterway") & (lines["class"] == "river")].copy()
    river["type"] = "river"
    frame = pd.concat([roads[["type", "geometry"]], river[["type", "geometry"]]])
    frame = gpd.GeoDataFrame(frame, geometry="geometry", crs=CRS_METRIC)
    frame["geometry"] = frame.simplify(15)
    return {
        "districts": geojson(districts, ["name_en"]),
        "lines": geojson(frame, ["type"]),
    }


def uncovered_points(points: pd.DataFrame, od: dict[str, pd.DataFrame]) -> dict[int, pd.Series]:
    dwellings = points[points["kind"] == "dwelling"].set_index("point_id")
    weight = dwellings[DEMAND["school"]].fillna(0.0)
    result = {}
    for radius in RADII_M:
        reached = covered(od["school"], radius)
        result[radius] = weight[~weight.index.isin(reached) & (weight > 0)]
    return result


def cells(points: pd.DataFrame, uncovered: dict[int, pd.Series]) -> dict:
    tables = {
        kind: pd.read_parquet(PROCESSED / f"access_cells_{kind}.parquet")
        for kind in ("school", "preschool")
    }
    index = sorted(set(tables["school"].index) | set(tables["preschool"].index))
    cell_of = points.set_index("point_id")["h3"]
    rows, rings = [], []
    lost = {
        radius: values.groupby(cell_of.reindex(values.index)).sum()
        for radius, values in uncovered.items()
    }
    means = {
        kind: float(np.average(table["a"], weights=table["w"])) for kind, table in tables.items()
    }
    for cell in index:
        row = [cell]
        for kind, table in tables.items():
            if cell in table.index:
                item = table.loc[cell]
                cluster = 1 if item["p"] < 0.05 and item["quadrant"] == "LL" else 0
                row += [
                    round(float(item["w"]), 1),
                    round(float(item["a"]) / means[kind], 3),
                    cluster,
                ]
            else:
                row += [0.0, None, 0]
        district = (
            tables["school"].at[cell, "district"]
            if cell in tables["school"].index
            else tables["preschool"].at[cell, "district"]
        )
        row += [round(float(lost[r].get(cell, 0.0)), 1) for r in RADII_M] + [district]
        rows.append(row)
        boundary = h3.cell_to_boundary(cell)
        rings.append([rounded(v) for lat, lon in boundary for v in (lon, lat)])
    return {
        "fields": [
            "h3",
            "school_children",
            "school_access",
            "school_cluster",
            "preschool_children",
            "preschool_access",
            "preschool_cluster",
            "uncovered_1000",
            "uncovered_1500",
            "district",
        ],
        "rows": rows,
        "rings": rings,
    }


def schools() -> list[dict]:
    frame = facilities()["school"].to_crs(CRS_GEO)
    register = school_register.linked().dropna(subset=["facility_id"])
    register = register.drop_duplicates("facility_id").set_index("facility_id")
    seats, _ = official_programme()
    capacity = supply_measures()["school"]["capacity"]
    records = []
    for row in frame.itertuples():
        official = register.loc[row.facility_id] if row.facility_id in register.index else None
        records.append(
            {
                "id": row.facility_id,
                "number": number(official["number"] if official is not None else row.number),
                "name": str(official["name"] if official is not None else (row.name or "")),
                "district": (official["district"] if official is not None else None),
                "capacity": number(capacity.get(row.facility_id)),
                "official": official is not None,
                "enrolment_2025": number(official["enrolment_2025"])
                if official is not None
                else None,
                "enrolment_2026": number(official["enrolment_2026"])
                if official is not None
                else None,
                "shifts": number(official["shifts"]) if official is not None else None,
                "programme": row.facility_id in seats,
                "presumed": bool(row.presumed_new),
                "lon": round(row.geometry.x, DIGITS),
                "lat": round(row.geometry.y, DIGITS),
            }
        )
    return records


def preschools() -> list[dict]:
    frame = gpd.read_file(PROCESSED / "facilities.gpkg", layer="preschools")
    frame = frame[frame.geometry.notna()].to_crs(CRS_GEO)
    capacity = supply_measures()["preschool"]["capacity"]
    attending = attendance_by_id()
    ids = pd.to_numeric(frame["indigo_id"], errors="coerce")
    return [
        {
            "id": row.facility_id,
            "name": str(row.name),
            "ownership": row.ownership,
            "district": row.district,
            "capacity": number(capacity.get(row.facility_id)),
            "attending": number(attending.get(indigo)) if pd.notna(indigo) else None,
            "free": number(row.free_places),
            "lon": round(row.geometry.x, DIGITS),
            "lat": round(row.geometry.y, DIGITS),
        }
        for row, indigo in zip(frame.itertuples(), ids, strict=True)
    ]


def sites() -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    plan = gpd.read_file(PROCESSED / "backtest.gpkg", layer="plan_2026_2028").to_crs(CRS_METRIC)
    pdp = gpd.read_file(PROCESSED / "backtest.gpkg", layer="pdp_schools").to_crs(CRS_METRIC)
    return plan, pdp


def reach(points, uncovered, plan, pdp) -> dict:
    network = load()
    new = plan[plan["kind"] == "new"].copy()
    candidates = pd.concat(
        [
            new[["facility_id", "geometry"]],
            pdp[["facility_id", "geometry"]],
        ],
        ignore_index=True,
    )
    candidates = gpd.GeoDataFrame(candidates, geometry="geometry", crs=CRS_METRIC)
    od = origin_destination(network, points, candidates, "facility_id")
    base = uncovered[RADII_M[0]]
    near = od[(od["distance_m"] <= max(RADII_M)) & od["point_id"].isin(base.index)]
    keep = sorted(set(near["point_id"]))
    position = {pid: i for i, pid in enumerate(keep)}
    children = [round(float(base[pid]), 2) for pid in keep]
    flags = [1 if pid in uncovered[RADII_M[1]].index else 0 for pid in keep]
    lists = {}
    for radius in RADII_M:
        valid = set(uncovered[radius].index)
        part = near[(near["distance_m"] <= radius) & near["point_id"].isin(valid)]
        lists[str(radius)] = {
            fid: sorted(position[p] for p in group["point_id"])
            for fid, group in part.groupby("facility_id")
        }
    return {
        "children": children,
        "uncovered_1500": flags,
        "sites": lists,
        "total_uncovered": {str(r): round(float(v.sum())) for r, v in uncovered.items()},
    }


def greedy(lists: dict[str, list[int]], children: list[float], ids: list[str]) -> list[dict]:
    weights = np.array(children)
    taken = np.zeros(len(weights), dtype=bool)
    remaining = [i for i in ids if i in lists]
    order = []
    total = 0.0
    while remaining:
        gains = [(float(weights[lists[i]][~taken[lists[i]]].sum()), i) for i in remaining]
        gain, best = max(gains)
        if gain <= 0:
            break
        taken[lists[best]] = True
        total += gain
        order.append({"id": best, "gain": round(gain), "cumulative": round(total)})
        remaining.remove(best)
    return order


def summary() -> dict:
    def report(name: str) -> dict:
        path = REPORTS / name
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    equity = report("access_equity.json")
    compliance = report("compliance.json").get("station_model", {})
    register = report("school_register_check.json")
    plan = report("plan_2026_2028.json")
    detailed = report("detailed_plans.json")
    programme = report("programme_2023.json")
    population = report("population_model.json")
    preschool = report("preschool_capacity_check.json")
    return {
        "official_population": OFFICIAL_2026,
        "equity": {
            kind: {
                key: equity.get(kind, {}).get(key)
                for key in (
                    "district_relative",
                    "gini",
                    "between_share",
                    "cold_spot_children_share",
                    "zero_access_share",
                )
            }
            for kind in ("school", "preschool")
        },
        "sensitivity": equity.get("sensitivity_by_population"),
        "compliance": compliance,
        "crowding": register.get("crowding"),
        "load_check": register.get("load_check"),
        "plan": {
            "seats_by_district": plan.get("seats_by_district"),
            "radii": {
                r: {k: v for k, v in item.items() if k in ("uncovered_children", "stages")}
                for r, item in plan.get("radii", {}).items()
            },
            "access": plan.get("access"),
        },
        "detailed_plans": {
            k: detailed.get(k) for k in ("school_objects", "at_existing_school", "planned_sites")
        }
        | {"radii": detailed.get("radii")},
        "programme": {
            "selection": programme.get("selection"),
            "capacitated": programme.get("capacitated"),
            "backtest": programme.get("backtest"),
        },
        "population_fit": {
            k: population.get("district_fit", {}).get(k)
            for k in ("worldpop", "floor_area", "stations_alpha_0.2")
        },
        "preschool": preschool.get("attendance", {}) | {"queue_city": preschool.get("queue_city")},
    }


def build() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    points, od = load_inputs()
    uncovered = uncovered_points(points, od)
    plan, pdp = sites()
    sizes = {"base.json": write("base.json", base_layers())}
    sizes["cells.json"] = write("cells.json", cells(points, uncovered))
    sizes["schools.json"] = write("schools.json", schools())
    sizes["preschools.json"] = write("preschools.json", preschools())
    matrix = reach(points, uncovered, plan, pdp)
    ranking = {
        str(r): greedy(matrix["sites"][str(r)], matrix["children"], list(pdp["facility_id"]))
        for r in RADII_M
    }
    plan_out = plan.to_crs(CRS_GEO)
    sizes["sites.json"] = write(
        "sites.json",
        {
            "plan": [
                {
                    "id": row.facility_id,
                    "code": row.plan_id,
                    "name": row.name,
                    "year": int(row.year),
                    "kind": row.kind,
                    "seats": float(row.seats),
                    "district": row.district,
                    "confidence": row.confidence,
                    "lon": round(row.geometry.x, DIGITS),
                    "lat": round(row.geometry.y, DIGITS),
                }
                for row in plan_out.itertuples()
            ],
            "pdp": [
                {
                    "id": row.facility_id,
                    "purpose": row.purpose,
                    "seats": number(row.seats),
                    "lon": round(row.geometry.x, DIGITS),
                    "lat": round(row.geometry.y, DIGITS),
                }
                for row in pdp.to_crs(CRS_GEO).itertuples()
            ],
            "ranking": ranking,
        },
    )
    sizes["reach.json"] = write("reach.json", matrix)
    sizes["summary.json"] = write("summary.json", summary())
    return sizes


if __name__ == "__main__":
    print(json.dumps(build(), indent=1))
