import argparse
import difflib
import re
import subprocess
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .io import ROOT

PASSES = {"a": (300, 4), "b": (400, 6), "c": (450, 3)}


def cache_dir(eo: str, root: Path = ROOT) -> Path:
    d = root / "raw" / "cache" / "ocr" / eo
    d.mkdir(parents=True, exist_ok=True)
    return d


def pdf_path(eo: str, root: Path = ROOT) -> Path:
    return root / "raw" / "cache" / f"{eo}.pdf"


def render(eo: str, page: int, dpi: int, root: Path = ROOT) -> Path:
    out = cache_dir(eo, root) / f"p{page:03d}-{dpi}"
    png = out.with_suffix(".png")
    if not png.is_file():
        subprocess.run(["pdftoppm", "-r", str(dpi), "-gray", "-png", "-singlefile", "-f", str(page), "-l", str(page),
                        str(pdf_path(eo, root)), str(out)], check=True)
    return png


def ocr_page(eo: str, page: int, which: str = "a", root: Path = ROOT) -> str:
    dpi, psm = PASSES[which]
    txt = cache_dir(eo, root) / f"p{page:03d}-{which}.txt"
    if txt.is_file():
        return txt.read_text(encoding="utf-8")
    png = render(eo, page, dpi, root)
    base = txt.with_suffix("")
    subprocess.run(["tesseract", str(png), str(base), "-l", "rus", "--psm", str(psm)], check=True,
                   capture_output=True)
    if which == "a":
        subprocess.run(["tesseract", str(png), str(base) + "-tsv", "-l", "rus", "--psm", str(psm), "tsv"],
                       check=True, capture_output=True)
    return txt.read_text(encoding="utf-8")


def page_count(eo: str, root: Path = ROOT) -> int:
    out = subprocess.run(["pdfinfo", str(pdf_path(eo, root))], check=True, capture_output=True, text=True).stdout
    return int(re.search(r"Pages:\s+(\d+)", out).group(1))


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace(" ", " ").replace("\t", " ")
    text = re.sub(r"(\w)-\n\s*(\w)", r"\1-\2", text)
    text = re.sub(r"[ \n]+", " ", text)
    return text.strip()


def words(text: str) -> list[str]:
    return normalize(text).split(" ")


def diff_words(a: str, b: str) -> list[str]:
    wa, wb = words(a), words(b)
    out = []
    for line in difflib.unified_diff(wa, wb, "pass-a", "pass-b", n=2, lineterm=""):
        out.append(line)
    return out


def changed(diff: list[str]) -> int:
    return sum(1 for l in diff if l[:1] in "+-" and not l.startswith(("+++", "---")))


def parse_pages(spec: str | None, total: int) -> list[int]:
    if not spec:
        return list(range(1, total + 1))
    pages: list[int] = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            pages += range(int(a), int(b) + 1)
        else:
            pages.append(int(part))
    return pages


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="pipeline.ocr")
    p.add_argument("eo")
    p.add_argument("pages", nargs="?")
    p.add_argument("--pass", dest="which", default="a", choices=["a", "b", "c", "ab"])
    p.add_argument("-j", type=int, default=4)
    a = p.parse_args(argv)
    pages = parse_pages(a.pages, page_count(a.eo))
    jobs = [(pg, w) for pg in pages for w in a.which]
    with ThreadPoolExecutor(a.j) as ex:
        for (pg, w), _ in zip(jobs, ex.map(lambda j: ocr_page(a.eo, j[0], j[1]), jobs)):
            print(f"{a.eo} стр. {pg} проход {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
