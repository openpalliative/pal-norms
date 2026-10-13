import argparse
import csv
import io
import re
import subprocess
import sys
from pathlib import Path

from . import ocr
from .io import ROOT, dump_yaml, read_yaml, today

CROP_DPI = 150


def acts_by_id(root: Path = ROOT) -> dict:
    return {a["id"]: a for a in read_yaml(root / "data" / "acts.yaml")["acts"]}


def page_list(spec: str) -> list[int]:
    if "-" in spec:
        a, b = spec.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(spec)]


def _pattern(marker: str) -> str:
    parts = [re.escape(w) for w in ocr.normalize(marker).split(" ")]
    return r"\s*".join(parts)


def cut(text: str, start: str, end: str) -> str:
    norm = ocr.normalize(text)
    m = re.search(_pattern(start), norm)
    if not m:
        raise LookupError(f"не нашёл начало: {start!r}")
    e = re.search(_pattern(end), norm[m.start():])
    if not e:
        raise LookupError(f"не нашёл конец: {end!r}")
    return norm[m.start(): m.start() + e.end()]


def structure(text: str) -> str:
    text = text.replace("\u2014", "\u2013")
    text = re.sub(r"; (?=\S)", ";\n", text)
    return re.sub(r": (?=[а-яё])", ":\n", text)


def tsv_words(eo: str, page: int, root: Path = ROOT) -> list[dict]:
    ocr.ocr_page(eo, page, "a", root)
    path = ocr.cache_dir(eo, root) / f"p{page:03d}-a-tsv.tsv"
    rows = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8")), delimiter="\t", quoting=csv.QUOTE_NONE))
    return [r for r in rows if r.get("level") == "5" and (r.get("text") or "").strip()]


def _key(w: str) -> str:
    return re.sub(r"[^0-9a-zа-яё]", "", w.lower())


def _find(keys: list[str], probe: list[str], start: int = 0) -> int | None:
    for i in range(start, len(keys)):
        if not keys[i]:
            continue
        window = [k for k in keys[i: i + 12] if k][: len(probe)]
        if window == probe:
            return i
    return None


def _find_end(keys: list[str], probe: list[str], start: int) -> int | None:
    i = _find(keys, probe, start)
    if i is None:
        return None
    j, seen = i, 0
    while j < len(keys) and seen < len(probe):
        if keys[j]:
            seen += 1
        j += 1
    return j - 1


def _closest_end(keys: list[str], probe: list[str], start: int, expected: int) -> int | None:
    best, i = None, start
    while True:
        j = _find_end(keys, probe, i)
        if j is None:
            return best
        if best is None or abs(j - expected) < abs(best - expected):
            best = j
        i = j + 1


def bbox(eo: str, page: int, fragment: str, root: Path = ROOT, starts: bool = True, ends: bool = True):
    ws = tsv_words(eo, page, root)
    if not ws:
        return None
    keys = [_key(w["text"]) for w in ws]
    frag = [k for k in (_key(x) for x in re.split(r"[\s-]+", fragment)) if k]
    i0 = _find(keys, frag[:4]) if starts else 0
    if i0 is None:
        i0 = 0
    i1 = _closest_end(keys, frag[-3:], i0, i0 + len(frag)) if ends else len(ws) - 1
    if i1 is None or i1 < i0:
        i1 = len(ws) - 1
    sel = ws[i0: i1 + 1]
    page_left = min(int(w["left"]) for w in ws)
    page_right = max(int(w["left"]) + int(w["width"]) for w in ws)
    return (page_left, min(int(w["top"]) for w in sel), page_right,
            max(int(w["top"]) + int(w["height"]) for w in sel))


def crop(eo: str, page: int, box: tuple[int, int, int, int], out: Path, root: Path = ROOT) -> Path:
    scale = CROP_DPI / ocr.PASSES["a"][0]
    pad = 40
    x0, y0, x1, y1 = box
    x, y = max(0, int((x0 - pad) * scale)), max(0, int((y0 - pad) * scale))
    w, h = int((x1 - x0 + 2 * pad) * scale), int((y1 - y0 + 2 * pad) * scale)
    out.parent.mkdir(parents=True, exist_ok=True)
    base = out.with_suffix("")
    subprocess.run(["pdftoppm", "-r", str(CROP_DPI), "-gray", "-png", "-singlefile", "-f", str(page), "-l", str(page),
                    "-x", str(x), "-y", str(y), "-W", str(w), "-H", str(h),
                    str(ocr.pdf_path(eo, root)), str(base)], check=True)
    return out


def make_quote(act: dict, qid: str, pages: list[int], start: str, end: str, point: str, anchor: str,
               root: Path = ROOT) -> dict:
    eo = act["eoNumber"]
    text_a = "\n".join(ocr.ocr_page(eo, p, "a", root) for p in pages)
    text_b = "\n".join(ocr.ocr_page(eo, p, "b", root) for p in pages)
    frag_a = cut(text_a, start, end)
    try:
        frag_b = cut(text_b, start, end)
    except LookupError:
        frag_b = ""
    diff = ocr.diff_words(frag_a, frag_b)
    n = ocr.changed(diff)
    diff_path = root / "raw" / "ocr-diff" / f"{qid}.diff"
    if n:
        diff_path.parent.mkdir(parents=True, exist_ok=True)
        diff_path.write_text("\n".join(diff) + "\n", encoding="utf-8")
    elif diff_path.is_file():
        diff_path.unlink()
    for i, p in enumerate(pages):
        box = bbox(eo, p, frag_a, root, starts=(i == 0), ends=(i == len(pages) - 1))
        if box is None:
            continue
        name = f"{qid}.png" if i == 0 else f"{qid}-{i + 1}.png"
        crop(eo, p, box, root / "raw" / "crops" / name, root)
    return {
        "id": qid, "verified": False, "verified_at": None, "source_ref": f"pravo-{act['id']}",
        "act_id": act["id"], "point": point, "anchor": anchor, "page": pages[0], "text": structure(frag_a),
        "text_source": "official_pdf", "ocr": {"passes": 2, "diff_lines": n, "dpi": [ocr.PASSES["a"][0], ocr.PASSES["b"][0]]},
        "scan_checked": None,
    }


def upsert(root: Path, quote: dict) -> Path:
    path = root / "data" / "quotes" / f"{quote['act_id']}.yaml"
    data = read_yaml(path) if path.is_file() else {"quotes": []}
    data["quotes"] = [q for q in data["quotes"] if q["id"] != quote["id"]] + [quote]
    dump_yaml(data, path)
    return path


def quote_ids(root: Path = ROOT) -> set:
    out = set()
    for path in (root / "data" / "quotes").glob("*.yaml"):
        out |= {q["id"] for q in read_yaml(path)["quotes"]}
    return out


def crops_for(qid: str, root: Path = ROOT) -> list[str]:
    d = root / "raw" / "crops"
    others = quote_ids(root) - {qid}
    names = [p.name for p in d.glob(f"{qid}*.png") if re.fullmatch(re.escape(qid) + r"(-\d+)?\.png", p.name)
             and p.name[:-4] not in others]
    return sorted(names, key=lambda n: (len(n), n))


def mark_verified(root: Path, qid: str, date: str, notes: str | None = None) -> dict:
    for path in sorted((root / "data" / "quotes").glob("*.yaml")):
        data = read_yaml(path)
        for q in data["quotes"]:
            if q["id"] != qid:
                continue
            crops = crops_for(qid, root)
            if not crops:
                raise LookupError(f"нет вырезки raw/crops/{qid}.png")
            q["verified"], q["verified_at"] = True, date
            prev = q.get("scan_checked") or {}
            q["scan_checked"] = {"at": date, "method": "visual-crop", "crop": crops[0], "crops": crops,
                                 "notes": notes or prev.get("notes"), "second": prev.get("second")}
            dump_yaml(data, path)
            return q
    raise LookupError(f"нет цитаты {qid}")


SUP = str.maketrans({"¹": "", "²": "", "³": "", "⁴": "", "⁵": "", "⁶": "", "⁷": "", "⁸": "", "⁹": "", "⁰": ""})


def _cmp_key(w: str) -> str:
    w = w.translate(SUP).lower().replace("ё", "е").replace("—", "–")
    return re.sub(r"[«»\"“”„'`]", "", w)


def align(page_text: str, quote_text: str) -> list[str]:
    import difflib
    pw, qw = ocr.words(page_text), ocr.words(quote_text)
    pk, qk = [_cmp_key(w) for w in pw], [_cmp_key(w) for w in qw]
    blocks = [b for b in difflib.SequenceMatcher(None, pk, qk, autojunk=False).get_matching_blocks() if b.size >= 2]
    if not blocks:
        return []
    first, last = blocks[0], blocks[-1]
    a0 = max(0, first.a - first.b)
    a1 = min(len(pw), last.a + last.size + (len(qw) - last.b - last.size))
    return pw[a0:a1]


def second_diff(eo: str, pages: list[int], text: str, root: Path = ROOT) -> list[str]:
    import difflib
    page_text = "\n".join(ocr.ocr_page(eo, p, "c", root) for p in pages)
    frag = align(page_text, text)
    qw = ocr.words(text)
    out = []
    sm = difflib.SequenceMatcher(None, [_cmp_key(w) for w in qw], [_cmp_key(w) for w in frag], autojunk=False)
    for tag, i0, i1, j0, j1 in sm.get_opcodes():
        if tag != "equal":
            out.append(f"{tag}\tцитата: {' '.join(qw[i0:i1])}\tпроход c: {' '.join(frag[j0:j1])}")
    return out


def run_second(root: Path, qid: str, date: str, agrees: bool | None = None, notes: str | None = None) -> dict:
    acts = acts_by_id(root)
    for path in sorted((root / "data" / "quotes").glob("*.yaml")):
        data = read_yaml(path)
        for q in data["quotes"]:
            if q["id"] != qid:
                continue
            sc = q.get("scan_checked") or {}
            crops = sc.get("crops") or [sc.get("crop")]
            pages = [int(q["page"]) + i for i in range(len(crops))]
            diff = second_diff(acts[q["act_id"]]["eoNumber"], pages, q["text"], root)
            dpath = root / "raw" / "ocr-diff" / f"{qid}.second.tsv"
            dpath.write_text("\n".join(["вид\tцитата\tпроход c", *diff]) + "\n", encoding="utf-8")
            ok = (not diff) if agrees is None else agrees
            sc["second"] = {"at": date, "method": "ocr-pass-c", "agrees": ok, "crop": sc.get("crop"),
                            "notes": notes or (f"проход c ({ocr.PASSES['c'][0]} dpi, psm {ocr.PASSES['c'][1]}) "
                                               f"совпал со словами цитаты" if not diff else
                                               f"проход c: расхождений {len(diff)}, raw/ocr-diff/{qid}.second.tsv")}
            q["scan_checked"] = sc
            if not ok:
                q["verified"] = False
            dump_yaml(data, path)
            return {"id": qid, "diff": diff, "second": sc["second"]}
    raise LookupError(f"нет цитаты {qid}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="pipeline.quotes")
    sub = p.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add")
    add.add_argument("act_id")
    add.add_argument("pages")
    add.add_argument("start")
    add.add_argument("end")
    add.add_argument("--id", required=True)
    add.add_argument("--point", required=True)
    add.add_argument("--anchor", required=True)
    ver = sub.add_parser("verify")
    ver.add_argument("ids", nargs="+")
    ver.add_argument("--date", default=today())
    ver.add_argument("--notes")
    sec = sub.add_parser("second")
    sec.add_argument("ids", nargs="+")
    sec.add_argument("--date", default=today())
    sec.add_argument("--agrees", choices=["yes", "no"])
    sec.add_argument("--notes")
    sec.add_argument("--dry", action="store_true")
    a = p.parse_args(argv)
    if a.cmd == "second":
        for qid in a.ids:
            if a.dry:
                q = next(x for f in (ROOT / "data" / "quotes").glob("*.yaml") for x in read_yaml(f)["quotes"]
                         if x["id"] == qid)
                sc = q.get("scan_checked") or {}
                pages = [int(q["page"]) + i for i in range(len(sc.get("crops") or [1]))]
                diff = second_diff(acts_by_id()[q["act_id"]]["eoNumber"], pages, q["text"])
            else:
                agrees = None if a.agrees is None else a.agrees == "yes"
                diff = run_second(ROOT, qid, a.date, agrees, a.notes)["diff"]
            print(f"== {qid}: расхождений {len(diff)}")
            for d in diff:
                print("  " + d)
        return 0
    if a.cmd == "verify":
        for qid in a.ids:
            q = mark_verified(ROOT, qid, a.date, a.notes)
            print(f"{qid}: verified, вырезки {', '.join(q['scan_checked']['crops'])}")
        return 0
    act = acts_by_id()[a.act_id]
    q = make_quote(act, a.id, page_list(a.pages), a.start, a.end, a.point, a.anchor)
    upsert(ROOT, q)
    print(f"{q['id']}: расхождений {q['ocr']['diff_lines']}\n{q['text']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
