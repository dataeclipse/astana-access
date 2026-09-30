import html
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
import pandas as pd

from astana_access.config import RAW

HOST = "{number}.astana-bilim.kz"
CACHE = RAW / "school_sites"
USER_AGENT = "Mozilla/5.0 (compatible; astana-access/0.1; academic research)"
DELAY_S = 0.7
MAX_PAGES = 22
PLACEHOLDER_BYTES = 400
DISALLOWED = ("/options", "/cabinet", "/admin", "/company", "/crm", "/files", "/img", "/css", "/js")
SKIP_PATHS = ("/login", "/search", "/rss", "/systpls", "/news", "/gallery", "/photo")
STATIC = re.compile(r"\.(pdf|docx?|xlsx?|pptx?|jpe?g|png|gif|svg|ico|zip|rar|css|js|xml)$", re.I)
SEED_SLUGS = (
    "/passpoutschool",
    "/pasport1",
    "/pasport",
    "/passport",
    "/about_us",
    "/about-the-school",
    "/istorii",
    "/vizitka",
)

LINK_HINT = re.compile(
    r"pas+p|passport|pasport|about|istor|history|tarih|vizit|aina|info|mektep|school", re.I
)

NUM = r"(\d{1,2}[  ]?\d{3}|\d{3,4})"
CAPACITY = [
    re.compile(r"проектн\w*\s+м\s?ощност\w*(?:\s+\w+){0,3}?\s*[-–—:]?\s*(?:на\s+)?" + NUM, re.I),
    re.compile(r"жоба(?:лы[қк]|лау)\s+[қк]уат\w*(?:\s+\w+){0,3}?\s*[-–—:]?\s*" + NUM, re.I),
    re.compile(NUM + r"\s+орын[ғг]а\s+(?:есептел|арнал|лайы)", re.I),
    re.compile(r"рассчитан\w*\s+на\s+" + NUM + r"\s+(?:мест|учащ|учени|посадочн)", re.I),
    re.compile(NUM + r"\s+ученическ\w+\s+мест", re.I),
    re.compile(NUM + r"\s+орынды[қк]", re.I),
]
ENROLMENT = [
    re.compile(r"обуча\w+ся\s+" + NUM + r"\s+(?:учащ|учени|школьник|обучающ|дет)", re.I),
    re.compile(r"контингент\w*(?:\s+\w+){0,6}?\s*[-–—:]?\s*" + NUM, re.I),
    re.compile(NUM + r"\s+(?:учащихся|учеников|обучающихся)", re.I),
    re.compile(NUM + r"\s+о[қк]ушы", re.I),
]
SHIFTS = [
    re.compile(r"в\s+(одну|две|три|1|2|3)\s+смен", re.I),
    re.compile(r"(бір|екі|үш|1|2|3)\s+ауысым", re.I),
    re.compile(r"(одно|двух|трех)сменн", re.I),
]
SHIFT_VALUE = {
    "одну": 1,
    "одно": 1,
    "бір": 1,
    "1": 1,
    "две": 2,
    "двух": 2,
    "екі": 2,
    "2": 2,
    "три": 3,
    "трех": 3,
    "үш": 3,
    "3": 3,
}
YEAR = re.compile(r"(20[0-2]\d)\s*[-–—/]\s*(?:20)?([0-2]\d)\b")
AREA = re.compile(
    r"(?:общ\w+\s+площад\w*|жалпы\s+(?:к[өо]лемі|ауданы))(?:\s+\w+){0,4}?\s*[-–—:]?\s*"
    r"(\d{1,3}(?:[  ]?\d{3})*(?:[.,]\d+)?)\s*(?:кв\.?\s*м|м\.?\s*кв|м2|м²|м\s*2|ш\.?\s*м|шаршы|\b)",
    re.I,
)
HALL = re.compile(r"зал|асхана|столов|кітапхана|библиот|жатақхана|интернат", re.I)
CAPACITY_CONTEXT = re.compile(r"мощност|қуат|куат|рассчитан|орынды", re.I)


def fetch(url: str, target: Path, client: httpx.Client) -> str:
    if target.exists():
        return target.read_text(encoding="utf-8", errors="replace")
    try:
        response = client.get(url)
        text = response.text if response.status_code == 200 else ""
    except httpx.HTTPError:
        text = ""
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    time.sleep(DELAY_S)
    return text


def to_text(page: str) -> str:
    body = re.sub(r"<(script|style)\b.*?</\1>", " ", page, flags=re.S | re.I)
    body = html.unescape(re.sub(r"<[^>]+>", " ", body))
    return re.sub(r"\s+", " ", body).replace("ё", "е")


def candidate_links(page: str, base: str) -> list[str]:
    host = urlparse(base).netloc
    hinted: dict[str, None] = {}
    other: dict[str, None] = {}
    for href in re.findall(r"""href\s*=\s*["']?([^"' >#]+)""", page, flags=re.I):
        url = urljoin(base, html.unescape(href))
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or parsed.netloc != host:
            continue
        if parsed.path in ("", "/") or parsed.path.startswith(DISALLOWED + SKIP_PATHS):
            continue
        if STATIC.search(parsed.path):
            continue
        (hinted if LINK_HINT.search(url) else other).setdefault(url, None)
    seeds = [urljoin(base, slug + "?lang=ru") for slug in SEED_SLUGS]
    seen_paths = {urlparse(u).path.lower() for u in hinted}
    ordered = list(hinted) + [u for u in seeds if urlparse(u).path.lower() not in seen_paths]
    room = max(0, MAX_PAGES - len(ordered))
    ordered += list(other)[:room]
    return ordered[:MAX_PAGES]


def _row(
    number: int, field: str, value: float, pattern: int, text: str, span: tuple[int, int], url: str
) -> dict:
    start, end = max(0, span[0] - 140), min(len(text), span[1] + 140)
    window = text[start:end]
    year = YEAR.search(window)
    return {
        "number": number,
        "field": field,
        "value": value,
        "pattern": pattern,
        "year": int(year.group(1)) if year else None,
        "snippet": window.strip(),
        "url": url,
    }


def extract(text: str, url: str, number: int) -> list[dict]:
    rows = []
    for field, patterns, low, high in (
        ("capacity", CAPACITY, 100, 5000),
        ("enrolment", ENROLMENT, 100, 9000),
    ):
        for index, pattern in enumerate(patterns):
            for match in pattern.finditer(text):
                value = int(re.sub(r"\D", "", match.group(1)))
                if not low <= value <= high:
                    continue
                before = text[max(0, match.start() - 60) : match.start(1)]
                if field == "enrolment" and index >= 2 and CAPACITY_CONTEXT.search(before):
                    continue
                around = text[max(0, match.start() - 25) : match.end() + 30]
                if field == "capacity" and index >= 3 and HALL.search(around):
                    continue
                rows.append(_row(number, field, value, index, text, match.span(), url))
    for match in AREA.finditer(text):
        area = float(re.sub(r"[  ]", "", match.group(1)).replace(",", "."))
        if 500 <= area <= 80000:
            rows.append(_row(number, "total_area_m2", area, 0, text, match.span(), url))
    for pattern in SHIFTS:
        for match in pattern.finditer(text):
            value = SHIFT_VALUE.get(match.group(1).lower())
            if value is not None:
                rows.append(_row(number, "shifts", value, 0, text, match.span(), url))
    return rows


def crawl(numbers: list[int]) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict] = []
    status: list[dict] = []
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "ru,kk;q=0.8"}
    with httpx.Client(headers=headers, timeout=30, follow_redirects=True, verify=False) as client:
        for number in numbers:
            base = f"https://{HOST.format(number=number)}/"
            folder = CACHE / str(number)
            home = fetch(base + "?lang=ru", folder / "home.html", client)
            if len(home) < PLACEHOLDER_BYTES:
                status.append({"number": number, "site": False, "pages": 0, "title": ""})
                continue
            pages = [(base + "?lang=ru", home)]
            for link in candidate_links(home, base):
                slug = re.sub(r"[^a-zA-Z0-9]+", "_", urlparse(link).path).strip("_")[:60] or "root"
                page = fetch(link, folder / f"{slug}.html", client)
                if len(page) >= PLACEHOLDER_BYTES:
                    pages.append((link, page))
            title = re.search(r"<title[^>]*>(.*?)</title>", home, flags=re.S | re.I)
            status.append(
                {
                    "number": number,
                    "site": True,
                    "pages": len(pages),
                    "title": html.unescape(title.group(1)).strip()[:160] if title else "",
                }
            )
            for url, page in pages:
                rows.extend(extract(to_text(page), url, number))
    columns = ["number", "field", "value", "pattern", "year", "snippet", "url"]
    found = pd.DataFrame(rows, columns=columns).drop_duplicates(
        subset=["number", "field", "value", "snippet"]
    )
    return found, pd.DataFrame(status)


def run(numbers: list[int]) -> tuple[pd.DataFrame, pd.DataFrame]:
    found, status = crawl(numbers)
    CACHE.mkdir(parents=True, exist_ok=True)
    found.to_csv(CACHE / "extracted_raw.csv", index=False, encoding="utf-8-sig")
    status.to_csv(CACHE / "site_status.csv", index=False, encoding="utf-8-sig")
    return found, status
