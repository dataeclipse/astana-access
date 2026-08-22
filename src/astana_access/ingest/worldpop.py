from dataclasses import dataclass
from pathlib import Path

from astana_access.config import RAW
from astana_access.ingest.http import download

ISO3 = "kaz"
YEAR = 2025
RELEASE = "R2025A"
BASE_POP = (
    "https://data.worldpop.org/GIS/Population/Global_2015_2030/"
    f"{RELEASE}/{YEAR}/{ISO3.upper()}/v1/100m/constrained"
)
BASE_AGESEX = (
    "https://data.worldpop.org/GIS/AgeSex_structures/Global_2015_2030/"
    f"{RELEASE}/{YEAR}/{ISO3.upper()}/v1/100m/constrained"
)

AGE_BANDS = ["00", "01", "05", "10", "15"]


@dataclass(frozen=True)
class Layer:
    name: str
    url: str
    band_start: int
    band_end: int


def total_layer() -> Layer:
    filename = f"{ISO3}_pop_{YEAR}_CN_100m_{RELEASE}_v1.tif"
    return Layer("total", f"{BASE_POP}/{filename}", 0, 120)


def age_layers() -> list[Layer]:
    spans = {"00": (0, 0), "01": (1, 4), "05": (5, 9), "10": (10, 14), "15": (15, 19)}
    layers = []
    for band in AGE_BANDS:
        filename = f"{ISO3}_t_{band}_{YEAR}_CN_100m_{RELEASE}_v1.tif"
        start, end = spans[band]
        layers.append(Layer(f"t_{band}", f"{BASE_AGESEX}/{filename}", start, end))
    return layers


def fetch_all(force: bool = False) -> dict[str, Path]:
    target_dir = RAW / "worldpop"
    paths = {}
    for layer in [total_layer(), *age_layers()]:
        paths[layer.name] = download(layer.url, target_dir / Path(layer.url).name, force=force)
    return paths
