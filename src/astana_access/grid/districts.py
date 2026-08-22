import geopandas as gpd

from astana_access.config import CRS_GEO, PROCESSED, RAW

STALE_PARENTS = {"Есіл ауданы": ["Нұра ауданы"]}

NAME_EN = {
    "Есіл ауданы": "Esil",
    "Алматы ауданы": "Almaty",
    "Сарыарқа ауданы": "Saryarka",
    "Байқоңыр ауданы": "Baikonur",
    "Нұра ауданы": "Nura",
    "Сарайшық ауданы": "Saraishyk",
}


def build() -> gpd.GeoDataFrame:
    frame = gpd.read_file(RAW / "boundary" / "districts.geojson").to_crs(CRS_GEO)
    lookup = dict(zip(frame["name"], frame.geometry, strict=True))
    fixed = []
    for name, geometry in lookup.items():
        for child in STALE_PARENTS.get(name, []):
            if child in lookup:
                geometry = geometry.difference(lookup[child])
        fixed.append({"name": name, "name_en": NAME_EN.get(name, name), "geometry": geometry})
    result = gpd.GeoDataFrame(fixed, crs=CRS_GEO).sort_values("name_en").reset_index(drop=True)
    target = PROCESSED / "districts.gpkg"
    target.parent.mkdir(parents=True, exist_ok=True)
    result.to_file(target, layer="districts", driver="GPKG")
    return result


def validate(districts: gpd.GeoDataFrame, city: gpd.GeoDataFrame) -> dict[str, float]:
    metric = districts.to_crs("EPSG:32642")
    city_metric = city.to_crs("EPSG:32642").union_all()
    union = metric.union_all()
    overlap = sum(
        metric.geometry.iloc[i].intersection(metric.geometry.iloc[j]).area
        for i in range(len(metric))
        for j in range(i + 1, len(metric))
    )
    return {
        "districts": float(len(districts)),
        "sum_area_km2": float(metric.area.sum() / 1e6),
        "union_area_km2": float(union.area / 1e6),
        "city_area_km2": float(city_metric.area / 1e6),
        "pairwise_overlap_km2": float(overlap / 1e6),
        "uncovered_km2": float(city_metric.difference(union).area / 1e6),
    }
