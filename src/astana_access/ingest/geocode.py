import json
import time
from pathlib import Path

import httpx
from unidecode import unidecode

from astana_access.config import RAW, settings

CACHE = RAW / "geocode" / "nominatim_cache.json"
ASTANA_VIEWBOX = "71.20,51.36,71.80,50.85"


def _load_cache() -> dict[str, list[dict]]:
    if CACHE.exists():
        return json.loads(CACHE.read_text(encoding="utf-8"))
    return {}


def _save_cache(cache: dict[str, list[dict]]) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")


def search(query: str, cache: dict[str, list[dict]] | None = None) -> list[dict]:
    store = cache if cache is not None else _load_cache()
    if query in store:
        return store[query]
    response = httpx.get(
        settings.nominatim_url,
        params={
            "q": query,
            "format": "jsonv2",
            "limit": 3,
            "viewbox": ASTANA_VIEWBOX,
            "bounded": 1,
            "addressdetails": 1,
        },
        headers={"User-Agent": settings.user_agent},
        timeout=settings.request_timeout,
    )
    response.raise_for_status()
    store[query] = response.json()
    time.sleep(max(settings.request_delay, 1.1))
    if cache is None:
        _save_cache(store)
    return store[query]


def address_variants(street: str, housenumber: str) -> list[str]:
    base = street.strip()
    variants = [
        f"{base} {housenumber}, Астана",
        f"{base}, {housenumber}, Astana",
        f"{unidecode(base)} {housenumber}, Astana",
        f"{base}, Астана",
    ]
    return list(dict.fromkeys(variants))


def geocode_address(street: str, housenumber: str) -> dict | None:
    cache = _load_cache()
    try:
        for query in address_variants(street, housenumber):
            hits = search(query, cache)
            if hits:
                hit = hits[0]
                exact = housenumber.split("/")[0] in str(
                    hit.get("address", {}).get("house_number", "")
                )
                return {
                    "query": query,
                    "lat": float(hit["lat"]),
                    "lon": float(hit["lon"]),
                    "display_name": hit.get("display_name"),
                    "osm_class": hit.get("category") or hit.get("class"),
                    "match_level": "house"
                    if exact
                    else ("street" if query.endswith(("Астана", "Astana")) else "other"),
                }
        return None
    finally:
        _save_cache(cache)


def cache_path() -> Path:
    return CACHE
