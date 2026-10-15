import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import httpx
from rapidfuzz import fuzz

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "thesis" / "bib"
CACHE = ROOT / "data" / "raw" / "references_cache.json"
MAILTO = "diasbolatov1337@gmail.com"
HEADERS = {"User-Agent": f"astana-access/0.1 (mailto:{MAILTO})"}


@dataclass
class Candidate:
    key: str
    title: str
    author: str
    year: int
    kind: str
    sections: str
    doi: str = ""
    purpose: str = ""


@dataclass
class Verified:
    key: str
    status: str
    kind: str
    sections: str
    purpose: str
    doi: str = ""
    title: str = ""
    authors: str = ""
    year: int | None = None
    venue: str = ""
    title_score: float = 0.0
    article_number: str = ""
    bibtex: str = ""
    notes: list[str] = field(default_factory=list)


def load_cache() -> dict:
    return json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}


def save_cache(cache: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")


def get(url: str, cache: dict, accept: str | None = None) -> tuple[int, str]:
    token = f"{accept}|{url}"
    if token in cache:
        return cache[token][0], cache[token][1]
    headers = dict(HEADERS)
    if accept:
        headers["Accept"] = accept
    for attempt in range(3):
        try:
            response = httpx.get(url, headers=headers, timeout=60, follow_redirects=True)
            cache[token] = [response.status_code, response.text]
            time.sleep(0.4)
            return response.status_code, response.text
        except httpx.HTTPError:
            time.sleep(3 * (attempt + 1))
    return 0, ""


def crossref_work(doi: str, cache: dict) -> dict | None:
    status, text = get(f"https://api.crossref.org/works/{doi}?mailto={MAILTO}", cache)
    if status != 200:
        return None
    return json.loads(text)["message"]


def crossref_search(candidate: Candidate, cache: dict) -> dict | None:
    query = httpx.QueryParams(
        {
            "query.bibliographic": f"{candidate.title} {candidate.author}",
            "rows": 8,
            "mailto": MAILTO,
        }
    )
    status, text = get(f"https://api.crossref.org/works?{query}", cache)
    if status != 200:
        return None
    best, best_score = None, 0.0
    for item in json.loads(text)["message"]["items"]:
        score = match_score(candidate, item)
        if score > best_score:
            best, best_score = item, score
    return best if best_score >= 80 else None


def item_title(item: dict) -> str:
    return re.sub(r"<[^>]+>", "", (item.get("title") or [""])[0])


def item_year(item: dict) -> int | None:
    for key in ("published-print", "published-online", "issued", "created"):
        parts = item.get(key, {}).get("date-parts") or [[None]]
        if parts and parts[0] and parts[0][0]:
            return int(parts[0][0])
    return None


def item_authors(item: dict) -> list[str]:
    names = []
    for author in item.get("author", []) or []:
        names.append(author.get("family") or author.get("name") or "")
    return names


def clean(text: str) -> str:
    return re.sub(r"[^\w\s]", " ", text.lower())


def match_score(candidate: Candidate, item: dict) -> float:
    full = item_title(item) + " " + " ".join(item.get("subtitle") or [])
    title = fuzz.token_set_ratio(clean(candidate.title), clean(full))
    surnames = " ".join(item_authors(item)).lower()
    author_ok = candidate.author.lower() in surnames if candidate.author else True
    year = item_year(item)
    year_ok = year is not None and abs(year - candidate.year) <= 1
    return title * (1.0 if author_ok else 0.6) * (1.0 if year_ok else 0.7)


def fetch_bibtex(doi: str, cache: dict) -> str:
    status, text = get(
        f"https://doi.org/{doi}", cache, accept="application/x-bibtex; charset=utf-8"
    )
    return text.strip() if status == 200 and text.lstrip().startswith("@") else ""


def verify(candidate: Candidate, cache: dict) -> Verified:
    result = Verified(
        candidate.key, "unverified", candidate.kind, candidate.sections, candidate.purpose
    )
    item = crossref_work(candidate.doi, cache) if candidate.doi else None
    if item is not None and match_score(candidate, item) < 80:
        result.notes.append(f"supplied DOI {candidate.doi} did not match, searched instead")
        item = None
    if item is None:
        item = crossref_search(candidate, cache)
        if (
            item is not None
            and candidate.doi
            and item.get("DOI", "").lower() != candidate.doi.lower()
        ):
            result.notes.append(f"resolved to different DOI than supplied {candidate.doi}")
    if item is None:
        result.notes.append("no Crossref record matched title, first author and year")
        return result
    result.doi = item.get("DOI", "")
    result.title = item_title(item)
    result.authors = "; ".join(item_authors(item))
    result.year = item_year(item)
    result.venue = (item.get("container-title") or [item.get("publisher", "")])[0]
    result.title_score = fuzz.token_set_ratio(candidate.title.lower(), result.title.lower())
    result.article_number = str(item.get("article-number") or "")
    result.bibtex = fetch_bibtex(result.doi, cache)
    result.status = "verified" if result.bibtex else "metadata_only"
    return result


def title_case_if_shouting(value: str) -> str:
    letters = [c for c in value if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) > 0.8:
        small = {"on", "of", "and", "the", "in", "for", "a", "an", "to"}
        words = value.lower().split()
        return " ".join(
            w if (i and w in small) else w[:1].upper() + w[1:] for i, w in enumerate(words)
        )
    return value


def rekey(bibtex: str, key: str, year: int | None = None, article_number: str = "") -> str:
    text = re.sub(
        r"^@(\w+)\{[^,]*,", lambda m: f"@{m.group(1).lower()}{{{key},", bibtex.strip(), count=1
    )
    text = text.replace("&amp;", "\\&").replace("–", "--").replace("—", "---")
    text = text.replace("‐", "-").replace("‑", "-").replace("ε", r"$\varepsilon$")
    text = re.sub(r"(title=\{[^{}]*?)(?<!\\)%", r"\1\\%", text)
    if re.search(r"DOI=\{", text):
        text = re.sub(r",\s*url=\{http://dx\.doi\.org/[^}]*\}", "", text)
    text = re.sub(r",\s*ISSN=\{[^}]*\}", "", text)
    text = re.sub(r",\s*month=[A-Za-z]+", "", text)
    text = re.sub(
        r"title=\{([^}]*)\}",
        lambda m: "title={" + title_case_if_shouting(m.group(1)) + "}",
        text,
        count=1,
    )
    text = re.sub(
        r"author=\{([^}]*)\}",
        lambda m: "author={" + title_case_if_shouting(m.group(1)) + "}",
        text,
        count=1,
    )
    if year is not None:
        text = re.sub(r"year=\{\d{4}\}", f"year={{{year}}}", text)
    if article_number and not re.search(r"pages=\{", text):
        text = re.sub(r"\s*\}\s*$", f", eid={{{article_number}}} }}", text)
    return text


def assemble() -> None:
    parts = [
        "% Generated by scripts/build_references.py. Do not edit by hand.",
        (OUT_DIR / "verified_crossref.bib").read_text(encoding="utf-8").strip(),
        (OUT_DIR / "manual.bib").read_text(encoding="utf-8").strip(),
    ]
    (OUT_DIR / "references.bib").write_text("\n\n".join(parts) + "\n", encoding="utf-8")


def main() -> None:
    catalog = json.loads((ROOT / "thesis" / "bib" / "candidates.json").read_text(encoding="utf-8"))
    candidates = [Candidate(**row) for row in catalog]
    cache = load_cache()
    results = []
    try:
        for candidate in candidates:
            if candidate.kind in {"manual_book", "manual_proceedings", "internet"}:
                results.append(
                    Verified(
                        candidate.key,
                        "manual",
                        candidate.kind,
                        candidate.sections,
                        candidate.purpose,
                        title=candidate.title,
                        authors=candidate.author,
                        year=candidate.year,
                    )
                )
                continue
            result = verify(candidate, cache)
            results.append(result)
            print(
                f"{result.status:<13} {candidate.key:<28} {result.title_score:5.0f}  {result.doi}",
                flush=True,
            )
    finally:
        save_cache(cache)
    (OUT_DIR / "verification.json").write_text(
        json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=1), encoding="utf-8"
    )
    entries = [
        rekey(r.bibtex, r.key, r.year, r.article_number) for r in results if r.status == "verified"
    ]
    (OUT_DIR / "verified_crossref.bib").write_text("\n\n".join(entries) + "\n", encoding="utf-8")
    assemble()
    counts = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    print(counts, file=sys.stderr)


if __name__ == "__main__":
    main()
