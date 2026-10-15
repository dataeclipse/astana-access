import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "dashboard"
FILES = ("base", "cells", "schools", "preschools", "sites", "reach", "summary")
OUT = ROOT / "offline" / "astana_access_atlas.html"


def main() -> None:
    page = (ROOT / "index.html").read_text(encoding="utf-8")
    data = {
        name: json.loads((ROOT / "data" / f"{name}.json").read_text(encoding="utf-8"))
        for name in FILES
    }
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    marker = "<script>\n(function () {"
    assert page.count(marker) == 1
    page = page.replace(marker, f"<script>window.ATLAS_DATA = {payload};</script>\n{marker}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page, encoding="utf-8")
    print(f"{OUT} {OUT.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
