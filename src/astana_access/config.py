from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW = DATA / "raw"
INTERIM = DATA / "interim"
PROCESSED = DATA / "processed"
EXTERNAL = DATA / "external"
FIGURES = ROOT / "thesis" / "figures"
REPORTS = ROOT / "reports"

CRS_GEO = "EPSG:4326"
CRS_METRIC = "EPSG:32642"

H3_RESOLUTION = 9

SEED = 20260825

CITY_NAME = "Astana"
CITY_OSM_RELATION = 4526735

SNAPSHOT_DATE = "2026-08-25"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    overpass_url: str = "https://overpass-api.de/api/interpreter"
    nominatim_url: str = "https://nominatim.openstreetmap.org/search"
    user_agent: str = "astana-access/0.1 (academic research)"
    osrm_url: str = "http://localhost:5000"
    twogis_api_key: str = ""
    request_timeout: int = 60
    request_delay: float = 1.0


settings = Settings()


def ensure_dirs() -> None:
    for path in (RAW, INTERIM, PROCESSED, EXTERNAL, FIGURES, REPORTS):
        path.mkdir(parents=True, exist_ok=True)
