import hashlib
import time
from pathlib import Path

import httpx
from tqdm import tqdm

from astana_access.config import settings


def download(url: str, target: Path, force: bool = False) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not force:
        return target
    partial = target.with_suffix(target.suffix + ".part")
    with httpx.stream("GET", url, follow_redirects=True, timeout=None) as response:
        response.raise_for_status()
        total = int(response.headers.get("content-length", 0))
        bar = tqdm(total=total, unit="B", unit_scale=True, desc=target.name, leave=False)
        with partial.open("wb") as handle:
            for chunk in response.iter_bytes(chunk_size=1 << 20):
                handle.write(chunk)
                bar.update(len(chunk))
        bar.close()
    partial.replace(target)
    return target


def post_json(url: str, data: dict[str, str], retries: int = 3) -> dict:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            response = httpx.post(
                url,
                data=data,
                timeout=settings.request_timeout * 4,
                headers={"User-Agent": settings.user_agent},
            )
            response.raise_for_status()
            return response.json()
        except Exception as error:
            last = error
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"request to {url} failed after {retries} attempts") from last


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
