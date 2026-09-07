import json
from typing import Any

import httpx
import pandas as pd

from astana_access.config import RAW, settings

INDEXES = {
    "kindergartens": "v1",
    "rosogrz_mp": "v1",
}

PAGE_SIZE = 100


def _request(index: str, version: str, source: dict[str, Any] | None = None) -> list[dict]:
    if not settings.egov_api_key:
        raise RuntimeError("EGOV_API_KEY is not set; add it to .env")
    params: dict[str, str] = {"apiKey": settings.egov_api_key}
    if source is not None:
        params["source"] = json.dumps(source, ensure_ascii=False)
    response = httpx.get(
        f"{settings.egov_api_url}/{index}/{version}",
        params=params,
        timeout=settings.request_timeout * 4,
        headers={"User-Agent": settings.user_agent},
    )
    if response.status_code >= 400:
        raise RuntimeError(f"{index}/{version}: HTTP {response.status_code}")
    payload = response.json()
    if isinstance(payload, dict):
        if "error" in payload:
            raise RuntimeError(f"{index}: {payload['error']}")
        return payload.get("hits", payload.get("data", []))
    return payload


def probe(index: str, version: str = "v1") -> list[dict]:
    return _request(index, version, {"size": 5})


def fetch(index: str, version: str = "v1") -> pd.DataFrame:
    rows: list[dict] = []
    offset = 0
    while True:
        batch = _request(index, version, {"from": offset, "size": PAGE_SIZE})
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    frame = pd.json_normalize(rows)
    target = RAW / "egov" / f"{index}.parquet"
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(target, index=False)
    return frame
