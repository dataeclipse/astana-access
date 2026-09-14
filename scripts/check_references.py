import collections
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIB = ROOT / "thesis" / "bib" / "references.bib"
SECTIONS = ROOT / "thesis" / "sections"
CATALOG = ROOT / "thesis" / "bib" / "candidates.json"
GREY = {"internet", "report"}


def main() -> None:
    bib = BIB.read_text(encoding="utf-8")
    entries = re.findall(r"^@(\w+)\{([^,]+),", bib, re.M)
    keys = [k for _, k in entries]
    counts = collections.Counter(keys)
    catalog = {row["key"]: row for row in json.loads(CATALOG.read_text(encoding="utf-8"))}
    tex = "".join(p.read_text(encoding="utf-8") for p in SECTIONS.glob("*.tex"))
    cited = {
        k.strip() for group in re.findall(r"\\cite[a-z]*\{([^}]+)\}", tex) for k in group.split(",")
    }

    grey = [k for k in keys if catalog.get(k, {}).get("kind") in GREY]
    academic = [k for k in keys if k not in grey]
    cited_grey = [k for k in cited if k in grey]

    print(f"entries {len(entries)}: {dict(collections.Counter(t for t, _ in entries))}")
    print(f"duplicate keys: {[k for k, c in counts.items() if c > 1]}")
    share = 100 * len(grey) / len(keys)
    print(f"academic {len(academic)}, internet or grey {len(grey)}, share {share:.1f} percent")
    print(f"cited in text: {len(cited)}")
    print(f"cited but missing from bib: {sorted(cited - set(keys))}")
    print(f"cited internet or grey: {len(cited_grey)} of {len(cited)}")
    print(f"placeholder authors left: {bib.count('Anonymous')}")
    print(f"all caps titles left: {len(re.findall(r'title=\{[A-Z0-9 ,.:;-]{12,}\}', bib))}")
    unusual = sorted({c for c in bib if ord(c) > 127 and not c.isalpha()})
    print(f"non-ASCII non-letter characters: {unusual}")


if __name__ == "__main__":
    main()
