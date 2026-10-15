import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THESIS = ROOT / "thesis"
OUT = ROOT / "thesis_overleaf.zip"
LATEXMKRC = "$pdf_mode = 5;\n$bibtex_use = 0;\n$max_repeat = 1;\n"
PREBUILT = ("main.bbl", "main.aux", "main.toc", "main.out")


def main() -> None:
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_thesis.py")], check=True)
    files = [THESIS / "main.tex", THESIS / "bib" / "references.bib"]
    files += sorted((THESIS / "sections").glob("*.tex"))
    files += sorted((THESIS / "figures").glob("*.pdf"))
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(THESIS).as_posix())
        for name in PREBUILT:
            archive.write(THESIS / "build" / name, name)
        archive.writestr("latexmkrc", LATEXMKRC)
    print(f"{OUT} {OUT.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
