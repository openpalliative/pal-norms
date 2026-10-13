import argparse
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import fetch_pravo, ocr
from .io import ROOT
from .pravo import Client


def find(client: Client, query: str, block: str, after: str, title_re: str | None, published: tuple = ()) -> list[dict]:
    extra = {"PublishDateSearchType": 0, "PublishDateFrom": published[0], "PublishDateTo": published[1]} if published else {}
    items = client.search_all(100, 10, Name=query, Block=block, **extra)
    out = []
    for it in items:
        date = (it.get("documentDate") or it.get("publishDateShort") or "")[:10]
        title = re.sub(r"\s+", " ", it.get("complexName") or "")
        if date <= after or (title_re and not re.search(title_re, title)):
            continue
        out.append({"eoNumber": it["eoNumber"], "number": it.get("number") or "", "doc_date": date,
                    "pages": int(it.get("pagesCount") or 0), "title": title})
    return sorted(out, key=lambda d: d["doc_date"])


def scan(doc: dict, patterns: dict, root: Path, first: int = 0) -> dict:
    eo = doc["eoNumber"]
    pages = ocr.page_count(eo, root)
    if first:
        pages = min(pages, first)
    text = ""
    for p in range(1, pages + 1):
        text += "\n" + ocr.ocr_page(eo, p, "a", root)
    flat = re.sub(r"\s+", " ", re.sub(r"(\w)-\n(\w)", r"\1\2", text))
    hits, ctx = {}, []
    for name, rx in patterns.items():
        found = list(re.finditer(rx, flat, re.I))
        hits[name] = len(found)
        ctx += [flat[max(0, m.start() - 80): m.end() + 80] for m in found[:2]]
    return {**doc, "pages": pages, "hits": hits, "context": " | ".join(ctx)}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="pipeline.amend_scan")
    p.add_argument("--query", required=True)
    p.add_argument("--block", default="president")
    p.add_argument("--after", required=True)
    p.add_argument("--title", help="регулярное выражение для названия")
    p.add_argument("--pattern", action="append", required=True, help="имя=выражение")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("-j", type=int, default=4)
    p.add_argument("--published", nargs=2, metavar=("ДД.ММ.ГГГГ", "ДД.ММ.ГГГГ"))
    p.add_argument("--first-pages", type=int, default=0)
    a = p.parse_args(argv)
    patterns = dict(x.split("=", 1) for x in a.pattern)
    client = Client()
    docs = find(client, a.query, a.block, a.after, a.title, tuple(a.published or ()))
    for d in docs:
        fetch_pravo.save_meta(client, d["eoNumber"], ROOT)
        fetch_pravo.save_pdf(client, d["eoNumber"], ROOT)
    with ThreadPoolExecutor(a.j) as ex:
        rows = list(ex.map(lambda d: scan(d, patterns, ROOT, a.first_pages), docs))
    head = ["eoNumber", "number", "doc_date", "pages", *patterns, "context"]
    lines = ["\t".join(head)]
    for r in rows:
        ctx = r["context"].replace("\t", " ")
        lines.append("\t".join([r["eoNumber"], r["number"], r["doc_date"], str(r["pages"]),
                                *[str(r["hits"][k]) for k in patterns], ctx]))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    found = [r for r in rows if any(r["hits"].values())]
    print(f"документов {len(rows)}, с совпадениями {len(found)} -> {a.out}")
    for r in found:
        print(f"{r['eoNumber']}\t{r['number']}\t{r['doc_date']}\t{r['hits']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
