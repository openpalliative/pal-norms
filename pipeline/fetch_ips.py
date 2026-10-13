import argparse
import html
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from .io import ROOT, dump_yaml, read_yaml, sha256_bytes, today
from .pravo import USER_AGENT

CDX = "https://web.archive.org/cdx/search/cdx"
SUP = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
NOTE = re.compile(r"\s*\((?:В редакции|Дополнение|Утратил|Часть утратила|Пункт утратил)[^()]*(?:\([^()]*\)[^()]*)*\)")


def _get(url: str, timeout: float = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def latest_snapshot(nd: str) -> tuple[str, str] | None:
    q = urllib.parse.urlencode({"url": "pravo.gov.ru/proxy/ips/*", "filter": [f"urlkey:.*nd={nd}.*", "statuscode:200"],
                                "output": "json", "limit": "-50"}, doseq=True)
    rows = json.loads(_get(f"{CDX}?{q}").decode("utf-8") or "[]")
    best = None
    for row in rows[1:]:
        ts, original, length = row[1], row[2], row[-1]
        if "doc_itself" not in original or not length.isdigit() or int(length) < 20000:
            continue
        if best is None or ts > best[0]:
            best = (ts, original)
    if best is None:
        return None
    return best[0], f"https://web.archive.org/web/{best[0]}id_/{best[1]}"


def decode(raw: bytes) -> str:
    for enc in ("cp1251", "utf-8"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("неизвестная кодировка снимка")


def paragraphs(page: str) -> list[str]:
    body = page[page.find("<body"):] if "<body" in page else page
    out = []
    for chunk in re.split(r"</p\s*>", body, flags=re.I):
        chunk = re.sub(r"<(sup|span class=\"W9\")[^>]*>\s*([0-9]+)\s*</(sup|span)>", lambda m: m.group(2).translate(SUP),
                       chunk, flags=re.I)
        text = html.unescape(re.sub(r"<[^>]+>", "", chunk)).replace(" ", " ")
        text = re.sub(r"\s+", " ", NOTE.sub("", text)).strip()
        if text:
            out.append(text)
    return out


def article(paras: list[str], number: str) -> list[str]:
    start = next((i for i, p in enumerate(paras) if re.match(rf"Статья {re.escape(number)}\.", p)), None)
    if start is None:
        raise LookupError(f"нет статьи {number}")
    out = [paras[start]]
    for p in paras[start + 1:]:
        if re.match(r"Статья \d", p):
            break
        out.append(p)
    return out


def part(paras: list[str], number: str, part_no: str) -> str:
    art = article(paras, number)
    for p in art[1:]:
        if re.match(rf"{re.escape(part_no)}\. ", p):
            return p
    raise LookupError(f"нет части {part_no} статьи {number}")


def item(paras: list[str], number: str, part_no: str, item_no: str) -> str:
    art = article(paras, number)
    inside = False
    for p in art[1:]:
        if re.match(rf"{re.escape(part_no)}\. ", p):
            inside = True
            continue
        if inside and re.match(r"\d+\. ", p):
            break
        if inside and re.match(rf"{re.escape(item_no)}\) ", p):
            return p
    raise LookupError(f"нет пункта {item_no} части {part_no} статьи {number}")


def editions(page: str) -> list[tuple[str, str]]:
    text = html.unescape(re.sub(r"<[^>]+>", "", page)).replace("\u00a0", " ")
    m = re.search(r"\(В редакции федеральных законов([^)]*)\)", text)
    return re.findall(r"от\s*(\d{2}\.\d{2}\.\d{4})\s*№\s*([0-9]+-ФЗ)", m.group(1)) if m else []


def make_quote(act: dict, snapshot: Path, number: str, part_no: str, qid: str, anchor: str,
               item_no: str | None = None) -> dict:
    paras = paragraphs(decode(snapshot.read_bytes()))
    text = item(paras, number, part_no, item_no) if item_no else part(paras, number, part_no)
    point = f"п. {item_no} ч. {part_no} ст. {number}" if item_no else f"ч. {part_no} ст. {number}"
    return {
        "id": qid, "verified": False, "verified_at": None, "source_ref": f"ips-{act['id']}", "act_id": act["id"],
        "point": point, "anchor": anchor, "page": None, "text": text,
        "text_source": "ips_archive", "ocr": None, "scan_checked": None,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="pipeline.fetch_ips")
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("nd")
    f.add_argument("--out", type=Path)
    q = sub.add_parser("quote")
    q.add_argument("act_id")
    q.add_argument("snapshot", type=Path)
    q.add_argument("article")
    q.add_argument("part")
    q.add_argument("--id", required=True)
    q.add_argument("--anchor", required=True)
    q.add_argument("--item")
    a = p.parse_args(argv)
    if a.cmd == "fetch":
        found = latest_snapshot(a.nd)
        if not found:
            print("снимков с текстом не нашлось", file=sys.stderr)
            return 1
        ts, url = found
        body = _get(url)
        out = a.out or ROOT / "raw" / "ips" / f"{a.nd}-{ts}.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(body)
        print(f"{url}\t{sha256_bytes(body)}\t{len(body)}\t{today()}")
        return 0
    acts = {x["id"]: x for x in read_yaml(ROOT / "data" / "acts.yaml")["acts"]}
    quote = make_quote(acts[a.act_id], a.snapshot, a.article, a.part, a.id, a.anchor, a.item)
    path = ROOT / "data" / "quotes" / f"{a.act_id}.yaml"
    data = read_yaml(path) if path.is_file() else {"quotes": []}
    data["quotes"] = [x for x in data["quotes"] if x["id"] != quote["id"]] + [quote]
    dump_yaml(data, path)
    print(quote["text"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
