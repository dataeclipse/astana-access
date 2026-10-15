import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "thesis"
OUT = ROOT / "build"
TIMEOUT_S = 300


def find(tool: str) -> str:
    found = shutil.which(tool)
    if found:
        return found
    miktex = (
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "MiKTeX" / "miktex" / "bin" / "x64"
    )
    candidate = miktex / f"{tool}.exe"
    if candidate.exists():
        return str(candidate)
    sys.exit(f"{tool} not found; install MiKTeX or TeX Live")


def run(command: list[str]) -> None:
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT_S)
    if result.returncode != 0:
        log = OUT / "main.log"
        errors = [
            line
            for line in log.read_text(encoding="utf-8", errors="replace").splitlines()
            if line.startswith("!")
        ]
        sys.exit(f"{Path(command[0]).stem} failed: {errors[:3] or result.stdout[-800:]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the thesis PDF into thesis/build.")
    parser.add_argument("--engine", choices=("xelatex", "pdflatex"), default="xelatex")
    engine = find(parser.parse_args().engine)
    biber = find("biber")
    OUT.mkdir(exist_ok=True)
    latex = [
        engine,
        "-interaction=nonstopmode",
        "-halt-on-error",
        f"-output-directory={OUT}",
        "main.tex",
    ]
    run(latex)
    run([biber, f"--input-directory={OUT}", f"--output-directory={OUT}", "main"])
    run(latex)
    run(latex)
    log = (OUT / "main.log").read_text(encoding="utf-8", errors="replace")
    pages = next((line for line in log.splitlines() if line.startswith("Output written")), "")
    undefined = sum("undefined" in line and "Warning" in line for line in log.splitlines())
    overfull = sum(line.startswith("Overfull") for line in log.splitlines())
    print(f"{pages.strip()} undefined references: {undefined}, overfull boxes: {overfull}")


if __name__ == "__main__":
    main()
