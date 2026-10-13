import json
import re
import sys
from pathlib import Path

from opsite.data import BuildError, load_schema, validate

from . import export
from .io import ROOT, read_yaml

NUMBER_WORDS = {1: "одного|суточн", 2: "двух", 3: "трех|трёх", 5: "пяти", 7: "семи", 10: "десяти", 14: "четырнадцати",
                15: "пятнадцати", 20: "двадцати", 30: "тридцати", 90: "девяноста"}
EO = re.compile(r"^\d{16}$")


def value_in_text(value: int, text: str) -> bool:
    if re.search(rf"(?<!\d){value}(?!\d)", text):
        return True
    words = NUMBER_WORDS.get(value)
    return bool(words and re.search(words, text, re.I))


def by_id(env: dict) -> dict:
    return {it["id"]: it for it in env["items"]}


def _dupes(env: dict) -> list[str]:
    seen, out = set(), []
    for it in env["items"]:
        if it["id"] in seen:
            out.append(f"{env['dataset']}: повтор id {it['id']}")
        seen.add(it["id"])
    return out


def check_schemas(envs: dict, root: Path) -> list[str]:
    out = []
    for name, env in envs.items():
        try:
            validate(env, load_schema("envelope"), f"конверт {name}")
            validate(env, export.schema(root, name), f"датасет {name}")
        except BuildError as e:
            out.append(str(e))
        out += _dupes(env)
        ids = {s["id"] for s in env["source"]}
        out += [f"{name}/{it['id']}: источник {it['source_ref']} не описан в source"
                for it in env["items"] if it.get("source_ref") and it["source_ref"] not in ids]
        out += [f"{name}/{it['id']}: синтетический id в настоящих данных" for it in env["items"]
                if str(it["id"]).startswith("demo-")]
    return out


def check_acts(acts: dict, quotes: dict, lint: dict) -> list[str]:
    out = []
    for a in acts.values():
        w = f"acts/{a['id']}"
        eo = a.get("eoNumber")
        if eo and not EO.match(eo):
            out.append(f"{w}: eoNumber не из 16 цифр")
        if a["text_source"] == "official_pdf":
            if not eo:
                out.append(f"{w}: официальный PDF без eoNumber")
            elif a["url"] != f"http://publication.pravo.gov.ru/document/{eo}" or \
                    a["pdf_url"] != f"http://publication.pravo.gov.ru/file/pdf?eoNumber={eo}":
                out.append(f"{w}: url или pdf_url не собраны из eoNumber")
        for q in a["quote_ids"]:
            if q not in quotes:
                out.append(f"{w}: нет цитаты {q}")
        for key in ("supersedes", "superseded_by"):
            for other in a[key]:
                if other not in acts:
                    out.append(f"{w}: {key} ссылается на неизвестный акт {other}")
        for other in a["supersedes"]:
            if other in acts and a["id"] not in acts[other]["superseded_by"]:
                out.append(f"{w}: замена {other} не симметрична")
        for other in a["superseded_by"]:
            if other in acts and a["id"] not in acts[other]["supersedes"]:
                out.append(f"{w}: замена {other} не симметрична")
        for c in a["cites"]:
            if c["act_id"] not in acts:
                out.append(f"{w}: ссылка на неизвестный акт {c['act_id']}")
            if c.get("quote_id") and c["quote_id"] not in quotes:
                out.append(f"{w}: ссылка на неизвестную цитату {c['quote_id']}")
        if a["status"] == "repealed":
            b = a["status_basis"] or {}
            q = quotes.get(b.get("quote_id") or "")
            if b.get("act_id") not in acts or not q:
                out.append(f"{w}: у отменённого акта нет основания с цитатой")
            elif a["verified"] and not q["verified"]:
                out.append(f"{w}: акт проверен, а цитата-основание нет")
            if a["aliases"] and not any(r["kind"] == "repealed_act" and r["act_id"] == a["id"] for r in lint.values()):
                out.append(f"{w}: у отменённого акта с aliases нет правила проверки текста")
        if a["status"] == "in_force" and a["repealed_at"]:
            out.append(f"{w}: действующий акт с датой утраты силы")
        if a["verified"] and a["text_source"] != "official_pdf" and a["status"] != "repealed":
            out.append(f"{w}: проверенным может быть только акт с официальным PDF")
    seen: set = set()

    def walk(aid: str, path: tuple) -> None:
        if aid in path:
            out.append("цикл замен: " + " > ".join(path + (aid,)))
            return
        if (aid, path) in seen:
            return
        seen.add((aid, path))
        for nxt in acts.get(aid, {}).get("superseded_by", []):
            walk(nxt, path + (aid,))

    for aid in acts:
        walk(aid, ())
    return out


def check_quotes(quotes: dict, acts: dict, root: Path) -> list[str]:
    out = []
    for q in quotes.values():
        w = f"quotes/{q['id']}"
        if q["act_id"] not in acts:
            out.append(f"{w}: неизвестный акт {q['act_id']}")
        if q["verified"]:
            if q["text_source"] != "official_pdf":
                out.append(f"{w}: проверенной может быть только цитата из официального PDF")
            if not q["scan_checked"]:
                out.append(f"{w}: проверена без сверки со сканом")
            if not (root / "raw" / "crops" / f"{q['id']}.png").is_file():
                out.append(f"{w}: нет вырезки raw/crops/{q['id']}.png")
            if (q.get("ocr") or {}).get("diff_lines", 0) > 0 and not (root / "raw" / "ocr-diff" / f"{q['id']}.diff").is_file():
                out.append(f"{w}: есть расхождения OCR, но нет raw/ocr-diff/{q['id']}.diff")
    return out


def check_rules(rules: dict, acts: dict, quotes: dict, steps: dict) -> list[str]:
    out = []
    for r in rules.values():
        w = f"deadline-rules/{r['id']}"
        out += [f"{w}: неизвестный акт {n}" for n in r["norm_ids"] if n not in acts]
        out += [f"{w}: неизвестная цитата {q}" for q in r["quote_ids"] if q not in quotes]
        out += [f"{w}: неизвестная ступень {s}" for s in r["escalation_ids"] if s not in steps]
        texts = " ".join(quotes[q]["text"] for q in r["quote_ids"] if q in quotes)
        if not value_in_text(r["value"], texts):
            out.append(f"{w}: числа {r['value']} нет в тексте цитат")
        if r["ambiguous"] and not r["ambiguity_note"]:
            out.append(f"{w}: неоднозначное правило без пояснения")
        if r["verified"]:
            if not all(quotes.get(q, {}).get("verified") for q in r["quote_ids"]):
                out.append(f"{w}: правило проверено, а цитаты нет")
            if not all(acts.get(n, {}).get("status") == "in_force" for n in r["norm_ids"]):
                out.append(f"{w}: правило проверено, а норма не действует")
    return out


def check_misc(envs: dict, acts: dict, quotes: dict, rules: dict) -> list[str]:
    out = []
    for s in envs["escalation"]["items"]:
        out += [f"escalation/{s['id']}: неизвестный акт {n}" for n in s["norm_ids"] if n not in acts]
        out += [f"escalation/{s['id']}: неизвестная цитата {q}" for q in s["quote_ids"] if q not in quotes]
        out += [f"escalation/{s['id']}: неизвестное правило {r}" for r in s["rule_ids"] if r not in rules]
    for r in envs["lint-rules"]["items"]:
        for key in ("act_id", "suggest_act_id"):
            if r.get(key) and r[key] not in acts:
                out.append(f"lint-rules/{r['id']}: неизвестный акт {r[key]}")
        out += [f"lint-rules/{r['id']}: неизвестная цитата {q}" for q in r["quote_ids"] if q not in quotes]
        for p in r["patterns"] + ([r["context"]["pattern"]] if r["context"] else []):
            if "\\b" in p or "\\p{" in p:
                out.append(f"lint-rules/{r['id']}: \\b и \\p{{}} не работают одинаково в JS и Python")
            try:
                re.compile(p)
            except re.error as e:
                out.append(f"lint-rules/{r['id']}: ошибка в выражении {p}: {e}")
    rows = envs["indications"]["items"]
    for row in rows:
        if row["act_id"] not in acts:
            out.append(f"indications/{row['id']}: неизвестный акт")
    if rows and sum(1 for r in rows if r["verified"]) / len(rows) < 0.9:
        out.append("indications: проверено меньше 90% строк")
    for y in envs["calendar"]["items"]:
        out += [f"calendar/{y['id']}: неизвестная цитата {q}" for q in y["quote_ids"] if q not in quotes]
        if y["kind"] == "year" and y["verified"]:
            act = acts.get(y["decree_act_id"] or "")
            if not act or not act["verified"] or act["eoNumber"] != y["decree_eoNumber"]:
                out.append(f"calendar/{y['id']}: год проверен, а постановление нет")
            if not all(quotes.get(q, {}).get("verified") for q in y["quote_ids"]):
                out.append(f"calendar/{y['id']}: год проверен, а цитата постановления нет")
    for c in envs["changes"]["items"]:
        out += [f"changes/{c['id']}: неизвестный акт {a}" for a in c["related_act_ids"] if a not in acts]
    return out


def check_text_safety(root: Path) -> list[str]:
    out = []
    terr = [re.compile(p) for p in __import__("yaml").safe_load(
        (root / "opsite" / "lint" / "territories.yaml").read_text(encoding="utf-8"))["patterns"]]
    drugs = [ln.strip() for ln in (root / "opsite" / "lint" / "drugs.txt").read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.startswith("#")]
    for path in sorted((root / "data").rglob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        for p in terr:
            if p.search(text):
                out.append(f"{path.relative_to(root)}: строка про исключённую территорию")
        low = text.lower()
        out += [f"{path.relative_to(root)}: название препарата {d}" for d in drugs if d in low]
    return out


def check_reviews(root: Path, envs: dict) -> list[str]:
    out = []
    rdir = root / "data" / "review"
    sch = json.loads((root / "data" / "schema" / "review.schema.json").read_text(encoding="utf-8"))
    ids = {name: {it["id"] for it in envs[name]["items"]} for name in export.TARGET_KINDS.values()}
    for path in sorted(rdir.glob("*.yaml")) if rdir.is_dir() else []:
        doc = read_yaml(path) or {}
        doc = {**doc, "reviews": [{k: v for k, v in r.items() if v not in ("", None)} for r in doc.get("reviews") or []]}
        try:
            validate(doc, sch, f"ревью {path.name}")
        except BuildError as e:
            out.append(str(e))
            continue
        for r in doc["reviews"]:
            if r["target"] not in ids[export.TARGET_KINDS[r["target_kind"]]]:
                out.append(f"review/{path.name}: нет {r['target_kind']} {r['target']}")
    return out


def run(root: Path = ROOT) -> list[str]:
    envs = {e["dataset"]: e for e in export.datasets(root)}
    acts, quotes = by_id(envs["acts"]), by_id(envs["quotes"])
    rules, steps, lint = by_id(envs["deadline-rules"]), by_id(envs["escalation"]), by_id(envs["lint-rules"])
    return (check_schemas(envs, root) + check_acts(acts, quotes, lint) + check_quotes(quotes, acts, root)
            + check_rules(rules, acts, quotes, steps) + check_misc(envs, acts, quotes, rules)
            + check_text_safety(root) + check_reviews(root, envs))


def summary(root: Path = ROOT) -> dict:
    envs = {e["dataset"]: e for e in export.datasets(root)}
    return {name: {"items": e["counts"]["items"], "verified": e["counts"]["items"] - e["counts"]["unverified"]}
            for name, e in envs.items()}


def main() -> int:
    errors = run()
    for e in errors:
        print(e)
    print(json.dumps(summary(), ensure_ascii=False))
    print(f"Ошибок: {len(errors)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
