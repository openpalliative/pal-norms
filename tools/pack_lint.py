import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

TEXT_SUFFIXES = {".md", ".txt", ".yaml", ".yml", ".j2", ".html", ".json"}
NORM_CALL = re.compile(r"norm\(\s*['\"]([a-z0-9]+(?:-[a-z0-9]+)*)['\"]")


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "")
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub("[   \t]", " ", text)
    return re.sub(r"№ *", "№ ", text)


def _flags(flags: str | None) -> int:
    return re.I if flags and "i" in flags else 0


def _items(x) -> list:
    if isinstance(x, list):
        return x
    return (x or {}).get("items") or []


def _line_info(text: str, index: int) -> tuple[int, int, str]:
    line = text.count("\n", 0, index) + 1
    line_start = text.rfind("\n", 0, index) + 1
    line_end = text.find("\n", index)
    if line_end == -1:
        line_end = len(text)
    return line, index - line_start + 1, text[line_start:line_end]


def _context_ok(text: str, start: int, end: int, context: dict | None) -> bool:
    if not context:
        return True
    lo, hi = max(0, start - context["window"]), min(len(text), end + context["window"])
    return re.search(context["pattern"], text[lo:hi], re.I) is not None


def check_text(text: str, rules, acts=None) -> list[dict]:
    norm = normalize(text)
    out = []
    for order, rule in enumerate(_items(rules)):
        spans = []
        for pattern in rule["patterns"]:
            for m in re.finditer(pattern, norm, _flags(rule.get("flags"))):
                if m.end() > m.start():
                    spans.append((m.start(), m.end()))
        spans.sort(key=lambda s: (s[0], -s[1]))
        last_end = -1
        for start, end in spans:
            if start < last_end or not _context_ok(norm, start, end, rule.get("context")):
                continue
            last_end = end
            line, col, line_text = _line_info(norm, start)
            out.append({
                "rule_id": rule["id"], "kind": rule["kind"], "severity": rule["severity"], "line": line, "col": col,
                "start": start, "end": end, "fragment": norm[start:end], "context": line_text.strip(),
                "message": rule["message"], "act_id": rule.get("act_id"), "suggest_act_id": rule.get("suggest_act_id"),
                "quote_ids": rule.get("quote_ids") or [], "_order": order,
            })
    out.sort(key=lambda f: (f["start"], f["_order"]))
    known = {a["id"] for a in _items(acts)} if acts is not None else None
    for f in out:
        del f["_order"]
        if known is not None and f["suggest_act_id"] and f["suggest_act_id"] not in known:
            f["suggest_act_id"] = None
    return out


def check_norms(text: str, acts) -> list[dict]:
    by_id = {a["id"]: a for a in _items(acts)}
    out = []
    for m in NORM_CALL.finditer(text):
        act = by_id.get(m.group(1))
        if act is None:
            problem = "ссылка на неизвестный документ"
        elif act.get("status") != "in_force":
            problem = "ссылка на документ, который не действует"
        elif act.get("verified") is not True:
            problem = "ссылка на документ, реквизиты которого не проверены"
        else:
            continue
        line, col, _ = _line_info(text, m.start())
        out.append({"rule_id": "norm-ref", "kind": "norm_ref", "severity": "error", "line": line, "col": col,
                    "start": m.start(), "end": m.end(), "fragment": m.group(0), "message": problem,
                    "act_id": m.group(1)})
    return out


def files_of(paths: list[str]) -> list[Path]:
    out = []
    for p in map(Path, paths):
        if p.is_dir():
            out += sorted(f for f in p.rglob("*") if f.is_file() and f.suffix in TEXT_SUFFIXES)
        elif p.is_file():
            out.append(p)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pack_lint", description="Проверка текстов на ссылки на утратившие силу документы")
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--rules", required=True)
    ap.add_argument("--acts", required=True)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    rules = json.loads(Path(a.rules).read_text(encoding="utf-8"))
    acts = json.loads(Path(a.acts).read_text(encoding="utf-8"))
    report = []
    for f in files_of(a.paths):
        text = f.read_text(encoding="utf-8")
        for finding in check_text(text, rules, acts) + check_norms(text, acts):
            report.append({"file": f.as_posix(), **finding})
    if a.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    else:
        for r in report:
            print(f"{r['file']}:{r['line']}:{r['col']}: {r['severity']}: {r['message']} ({r['fragment']})")
        print(f"Находок: {len(report)}")
    return 1 if any(r["severity"] == "error" for r in report) else 0


if __name__ == "__main__":
    sys.exit(main())
