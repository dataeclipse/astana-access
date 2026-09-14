import json
import re
from pathlib import Path

from pybtex.database import parse_file

ROOT = Path(__file__).resolve().parents[1]

GROUPS = [
    (
        "Accessibility measures",
        [
            "hansen1959",
            "geurs2004",
            "talen1998",
            "radke2000",
            "luo2003",
            "luo2009",
            "wang2012",
            "mcgrail2012",
            "wan2012",
            "delamater2013",
            "neutens2015",
            "eldercare2025",
            "chengdu2024",
            "italy2022",
        ],
    ),
    ("Impedance and winter walking", ["winterwalk2021", "coldwalk2020"]),
    (
        "Equity and spatial statistics",
        ["delbosc2011", "lucas2016", "theil1967", "moran1950", "anselin1995", "rey2007"],
    ),
    (
        "Facility location and optimisation",
        [
            "hakimi1964",
            "revelle1970",
            "church1974",
            "church1976",
            "current1988",
            "owen1998",
            "farahani2012",
            "murray2016",
            "pizzolato2004",
            "deb2002",
            "mavrotas2009",
            "esrilocalloc",
        ],
    ),
    (
        "Machine learning and explainability",
        [
            "chen2016",
            "ke2017",
            "prokhorenkova2018",
            "lundberg2017",
            "lundberg2020",
            "li2022",
            "li2024",
            "saito2015",
            "tianjin2025",
            "schoolsiting2025",
        ],
    ),
    ("Validation under spatial dependence", ["roberts2017", "ploton2020", "wadoux2021"]),
    ("Record linkage", ["fellegi1969", "christen2012", "kuhn1955"]),
    (
        "Population and dasymetric mapping",
        ["tobler1979", "eicher2001", "mennis2003", "stevens2015", "tatem2017"],
    ),
    (
        "Grids, OpenStreetMap and routing",
        ["sahr2003", "haklay2010", "barrington2017", "boeing2017", "luxen2011", "h3"],
    ),
    ("Planning support systems", ["geertman2004", "waddell2002", "communityviz"]),
    (
        "Astana and Kazakhstan context",
        [
            "koch2014",
            "laszczkowski2016",
            "astana2025",
            "oecd2015kz",
            "comfortschool2022",
            "planningorder2026",
            "sprk2013",
        ],
    ),
    ("Data sources", ["worldpop2025", "osm2026", "egovschools", "egovstudents", "statgov2025"]),
]


def plain(text: str) -> str:
    return text.replace("{", "").replace("}", "").replace("\\&", "&").replace("|", "/")


def who(entry, catalog: dict) -> str:
    people = entry.persons.get("author", [])
    if not people:
        return plain(
            entry.fields.get("organization", "") or catalog.get(entry.key, {}).get("author", "")
        )
    first = plain(" ".join(people[0].last_names))
    if len(people) == 1:
        return first
    if len(people) == 2:
        return f"{first} and {plain(' '.join(people[1].last_names))}"
    return f"{first} et al."


def venue(entry) -> str:
    for field in ("journal", "booktitle", "publisher", "organization"):
        if field in entry.fields:
            return plain(entry.fields[field])
    return ""


def link(entry) -> str:
    doi = entry.fields.get("doi") or entry.fields.get("DOI")
    if doi:
        return f"[{doi}](https://doi.org/{doi})"
    if "url" in entry.fields:
        return f"[link]({entry.fields['url']})"
    return ""


def main() -> None:
    db = parse_file(ROOT / "thesis" / "bib" / "references.bib")
    catalog = {
        row["key"]: row
        for row in json.loads(
            (ROOT / "thesis" / "bib" / "candidates.json").read_text(encoding="utf-8")
        )
    }
    tex = "".join(
        p.read_text(encoding="utf-8") for p in (ROOT / "thesis" / "sections").glob("*.tex")
    )
    cited = {
        k.strip() for group in re.findall(r"\\cite[a-z]*\{([^}]+)\}", tex) for k in group.split(",")
    }
    seen: set[str] = set()
    lines: list[str] = []
    for title, keys in GROUPS:
        lines += [
            f"### {title}",
            "",
            "| Key | Reference | Venue | DOI or URL | Cited | Planned section |",
            "|---|---|---|---|---|---|",
        ]
        for key in keys:
            entry = db.entries[key]
            seen.add(key)
            year = entry.fields.get("year", "")
            title_text = plain(entry.fields.get("title", ""))
            reference = f"{who(entry, catalog)} ({year}). {title_text}"
            mark = "yes" if key in cited else ""
            planned = catalog.get(key, {}).get("sections", "")
            cells = [f"`{key}`", reference, venue(entry), link(entry), mark, planned]
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
    missing = set(db.entries) - seen
    if missing:
        raise SystemExit(f"ungrouped entries: {sorted(missing)}")
    (ROOT / "reports" / "_reference_tables.md").write_text("\n".join(lines), encoding="utf-8")
    uncited = sorted(k for k in db.entries if k not in cited)
    print(f"grouped {len(seen)}, cited {len(cited)}, not yet cited {len(uncited)}")
    print(" ".join(uncited))


if __name__ == "__main__":
    main()
