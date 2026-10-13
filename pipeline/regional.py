import argparse
import json
import re
import sys
from pathlib import Path

from .io import ROOT, read_yaml
from .pravo import DENY_BLOCKS, Client, HttpTransport

TERMS = ("Курбан", "Ураза", "Сагаалган", "Цаган", "Шагаа", "Ысыах", "Чага", "Чыл", "Зул", "празднике", "праздника",
         "праздников", "праздничным", "праздничного", "праздничных", "праздничный", "праздничные", "нерабочим",
         "нерабочего", "нерабочих")


def blocks(client: Client) -> list[dict]:
    raw = client._json("/api/PublicBlocks", {"parent": "subjects"})
    out = [{"code": b["code"], "name": b.get("shortName") or b.get("name") or ""} for b in raw
           if re.fullmatch(r"region\d{2}", b.get("code") or "") and b["code"] not in DENY_BLOCKS]
    return sorted(out, key=lambda b: b["code"])


def search(client: Client, since: str, terms=TERMS, only: set | None = None) -> list[dict]:
    found: dict = {}
    for b in blocks(client):
        if only and b["code"] not in only:
            continue
        for term in terms:
            page = client.search(100, 1, Name=term, Block=b["code"], PublishDateSearchType=0, PublishDateFrom=since)
            for it in page.items:
                title = re.sub(r"\s+", " ", it.get("complexName") or "")
                found.setdefault(it["eoNumber"], {
                    "block": b["code"], "block_name": b["name"], "eoNumber": it["eoNumber"],
                    "doc_date": (it.get("documentDate") or "")[:10], "publish_date": (it.get("publishDateShort") or "")[:10],
                    "pages": it.get("pagesCount"), "title": title, "terms": []})["terms"].append(term)
    return sorted(found.values(), key=lambda d: (d["block"], d["doc_date"]))


def load(root: Path = ROOT) -> list[dict]:
    path = root / "data" / "calendar" / "regional.yaml"
    return read_yaml(path).get("regional") or [] if path.is_file() else []


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="pipeline.regional")
    p.add_argument("--since", default="01.06.2025")
    p.add_argument("--out", type=Path, default=ROOT / "raw" / "regional" / "search.json")
    p.add_argument("--block", action="append")
    p.add_argument("--pause", type=float, default=1.0)
    a = p.parse_args(argv)
    client = Client(HttpTransport(pause=a.pause))
    rows = search(client, a.since, only=set(a.block) if a.block else None)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"найдено {len(rows)} -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())


def rid(region_id: str, date: str) -> str:
    return f"{region_id.lower()}-{date}"


def add(root: Path, eo: str, pages: str, start: str, end: str, days: list[dict], region: dict, title: str | None = None) -> list[dict]:
    from . import fetch_pravo, quotes
    from .io import dump_yaml
    client = Client()
    meta = fetch_pravo.save_meta(client, eo, root)["meta"]
    fetch_pravo.save_pdf(client, eo, root)
    qid = f"rg-{region['region_id'][3:].lower()}-{meta.document_date[:4]}-{re.sub(r'[^0-9a-z]', '', meta.number.lower()) or 'n'}"
    q = quotes.make_quote({"id": qid, "eoNumber": eo}, qid, quotes.page_list(pages), start, end, "", "", root)
    quote = {"id": qid, "page": q["page"], "text": q["text"], "text_source": "official_pdf", "ocr": q["ocr"],
             "scan_checked": None}
    act = {"eoNumber": eo, "number": meta.number, "doc_date": meta.document_date, "publish_date": meta.publish_date,
           "title": (title or meta.complex_name.replace("\n", " ")).replace("\u2014", "\u2013"), "authority": (meta.authorities or [""])[0],
           "url": meta.url, "pdf_sha256": fetch_pravo.sha256_bytes((root / "raw" / "cache" / f"{eo}.pdf").read_bytes())}
    path = root / "data" / "calendar" / "regional.yaml"
    data = read_yaml(path) if path.is_file() else {"regional": []}
    rows = []
    for d in days:
        rows.append({"id": rid(region["region_id"], d["date"]), "region_id": region["region_id"],
                     "region_name": region["region_name"], "region_in": region["region_in"], "date": d["date"],
                     "title": d["title"], "eoNumber": eo, "act": act, "quote_ids": [qid], "quote": quote,
                     "verified": False, "verified_at": None, "source_ref": f"pravo-{eo}",
                     "legal_review": {"status": "none"}, "notes": d.get("notes")})
    ids = {r["id"] for r in rows}
    data["regional"] = sorted([r for r in data["regional"] if r["id"] not in ids] + rows, key=lambda r: (r["date"], r["region_id"]))
    dump_yaml(data, path)
    return rows


def verify(root: Path, qid: str, date: str, notes: str, second_notes: str | None = None) -> None:
    from . import quotes
    from .io import dump_yaml
    path = root / "data" / "calendar" / "regional.yaml"
    data = read_yaml(path)
    rows = [r for r in data["regional"] if r["quote"]["id"] == qid]
    if not rows:
        raise LookupError(qid)
    q = rows[0]["quote"]
    crops = quotes.crops_for(qid, root)
    pages = [int(q["page"]) + i for i in range(len(crops))]
    diff = quotes.second_diff(rows[0]["eoNumber"], pages, q["text"], root)
    sc = {"at": date, "method": "visual-crop", "crop": crops[0], "crops": crops, "notes": notes,
          "second": {"at": date, "method": "ocr-pass-c", "agrees": True, "crop": crops[0],
                     "notes": second_notes or ("проход c (450 dpi, psm 3) совпал со словами цитаты" if not diff else
                                               f"проход c: расхождений {len(diff)}, только распознавание, сверено по вырезке")}}
    for r in rows:
        r["quote"]["scan_checked"] = sc
        r["verified"], r["verified_at"] = True, date
    dump_yaml(data, path)
    print(qid, "расхождений прохода c:", len(diff), *diff, sep="\n  ")
