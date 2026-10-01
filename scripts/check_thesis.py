import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "thesis"
CITE = re.compile(r"\\cite\{([^}]*)\}")
LABEL = re.compile(r"\\label\{([^}]*)\}")
REF = re.compile(r"\\(?:ref|eqref)\{([^}]*)\}")
FIGURE = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]*)\}")
KEY = re.compile(r"^@(\w+)\{([^,]+)", re.M)


def main() -> None:
    sections = sorted((ROOT / "sections").glob("*.tex"))
    text = "\n".join(path.read_text(encoding="utf-8") for path in sections)
    cited = {key.strip() for group in CITE.findall(text) for key in group.split(",")}
    entries = dict(
        (key, kind)
        for kind, key in KEY.findall((ROOT / "bib" / "references.bib").read_text(encoding="utf-8"))
    )
    online = {key for key, kind in entries.items() if kind == "online"}
    labels = set(LABEL.findall(text))
    refs = set(REF.findall(text))
    figures = set(FIGURE.findall(text))
    missing_figures = [
        f for f in figures if not any((ROOT / f).with_suffix(s).exists() for s in (".pdf", ".eps"))
    ]
    print(f"cited sources: {len(cited)}")
    print(f"missing in bibliography: {sorted(cited - set(entries))}")
    print(
        f"online sources cited: {len(cited & online)} ({len(cited & online) / max(len(cited), 1):.1%})"
    )
    print(f"unresolved references: {sorted(refs - labels)}")
    print(f"missing figures: {missing_figures}")


if __name__ == "__main__":
    main()
