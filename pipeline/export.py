import datetime as dt
import json
import os
import re
from pathlib import Path

from opsite.data import coerce, content_sha256, make_envelope

from . import calendar, regional
from .io import ROOT, read_yaml

REPO = "pal-norms"
DATA_LICENSE = "не охраняется авторским правом, подп. 1 п. 6 ст. 1259 ГК РФ (официальные документы)"
SCHEMA_VERSIONS = {"deadline-rules": "1.2.0", "acts": "1.1.0", "quotes": "1.2.0", "indications": "1.2.0",
                   "escalation": "1.1.0", "calendar": "1.1.0"}
NAMES = ["acts", "quotes", "deadline-rules", "calendar", "escalation", "indications", "lint-rules", "changes",
         "entrypoints"]


def schema(root: Path, name: str) -> dict:
    return json.loads((root / "data" / "schema" / f"{name}.schema.json").read_text(encoding="utf-8"))


def item_schema(root: Path, name: str) -> dict:
    return schema(root, name)["properties"]["items"]["items"]


def fixtures(root: Path) -> list[dict]:
    out = []
    for name in NAMES:
        path = root / "tests" / "fixtures" / f"{name}.json"
        if path.is_file():
            out.append(json.loads(path.read_text(encoding="utf-8")))
    return out


def load_quotes(root: Path) -> list[dict]:
    out = []
    for path in sorted((root / "data" / "quotes").glob("*.yaml")):
        out += read_yaml(path)["quotes"]
    return out


TARGET_KINDS = {"act": "acts", "rule": "deadline-rules", "escalation": "escalation", "quote": "quotes",
                "indication": "indications"}
REVIEW_KEY = {"acts": "review", "quotes": "review", "indications": "review", "deadline-rules": "legal_review",
              "escalation": "legal_review"}


def today() -> dt.date:
    env = os.environ.get("PN_TODAY", "").strip()
    return dt.date.fromisoformat(env) if env else dt.date.today()


def add_months(d: dt.date, months: int) -> dt.date:
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    last = (dt.date(year + (month == 12), month % 12 + 1, 1) - dt.timedelta(days=1)).day
    return dt.date(year, month, min(d.day, last))


def expires_at(reviewed_at: str, expires_after: str) -> str:
    m = re.fullmatch(r"\s*(\d+)\s*([dmy]?)\s*", str(expires_after or ""))
    if not reviewed_at or not m:
        return ""
    n, unit = int(m.group(1)), m.group(2) or "d"
    start = dt.date.fromisoformat(reviewed_at)
    end = start + dt.timedelta(days=n) if unit == "d" else add_months(start, n * (12 if unit == "y" else 1))
    return end.isoformat()


def review_status(r: dict, on: dt.date) -> dict:
    exp = r.get("expires_at") or expires_at(r.get("reviewed_at") or "", r.get("expires_after") or "")
    status = "ok" if r.get("verdict") == "ok" else "none"
    if status == "ok" and exp and dt.date.fromisoformat(exp) < on:
        status = "expired"
    return {"status": status, "role": r.get("role") or "", "reviewed_at": r.get("reviewed_at") or "",
            "expires_at": exp, "ref": r.get("ref") or ""}


def load_reviews(root: Path, on: dt.date | None = None) -> dict:
    on = on or today()
    out: dict = {}
    rdir = root / "data" / "review"
    for path in sorted(rdir.glob("*.yaml")) if rdir.is_dir() else []:
        for r in read_yaml(path).get("reviews") or []:
            kind = r.get("target_kind") or "rule"
            key = (TARGET_KINDS.get(kind, kind), r["target"])
            cur = review_status(r, on)
            prev = out.get(key)
            if prev is None or (cur["reviewed_at"] or "") >= (prev["reviewed_at"] or ""):
                out[key] = cur
    return out


def raw(root: Path) -> dict:
    return {
        "meta": read_yaml(root / "data" / "meta.yaml"),
        "acts": read_yaml(root / "data" / "acts.yaml")["acts"],
        "quotes": load_quotes(root),
        "deadline-rules": read_yaml(root / "data" / "deadline-rules.yaml")["rules"],
        "calendar": calendar.items(root),
        "escalation": read_yaml(root / "data" / "escalation.yaml")["steps"],
        "indications": read_yaml(root / "data" / "indications.yaml")["indications"],
        "lint-rules": read_yaml(root / "data" / "lint-rules.yaml")["rules"],
        "changes": read_yaml(root / "data" / "changes.yaml")["changes"],
        "entrypoints": read_yaml(root / "data" / "entrypoints.yaml")["entrypoints"],
    }


def derive(d: dict, root: Path) -> None:
    acts = {a["id"]: a for a in d["acts"]}
    reviews = load_reviews(root)
    for a in d["acts"]:
        a["cites_repealed"] = [c for c in a.get("cites") or [] if acts.get(c["act_id"], {}).get("status") == "repealed"]
        a["rule_ids"] = [r["id"] for r in d["deadline-rules"] if a["id"] in r["norm_ids"]]
    for (name, target), rev in reviews.items():
        for it in d.get(name) or []:
            if it["id"] == target:
                it[REVIEW_KEY[name]] = rev
    date = d["meta"]["data_date"]
    for e in d["entrypoints"]:
        e.setdefault("verified", "true")
        e.setdefault("verified_at", date)


def sources(d: dict) -> dict:
    out = {}
    for a in d["acts"]:
        if a.get("eoNumber"):
            out[f"pravo-{a['id']}"] = {
                "id": f"pravo-{a['id']}", "title": f"{a['number']}: {a['title']}", "url": a["url"],
                "eoNumber": a["eoNumber"], "retrieved_at": a.get("verified_at") or d["meta"]["data_date"],
                "license": DATA_LICENSE,
            }
        for m in a.get("amended_by") or []:
            out[f"pravo-{m['eoNumber']}"] = {
                "id": f"pravo-{m['eoNumber']}", "title": m["title"],
                "url": f"http://publication.pravo.gov.ru/document/{m['eoNumber']}", "eoNumber": m["eoNumber"],
                "retrieved_at": d["meta"]["data_date"], "license": DATA_LICENSE,
            }
        alt = a.get("alt_source") or {}
        if alt.get("snapshot_url"):
            out[f"ips-{a['id']}"] = {
                "id": f"ips-{a['id']}", "title": f"ИПС «Законодательство России», снимок web.archive.org: {a['title']}",
                "url": alt["snapshot_url"], "retrieved_at": alt["retrieved_at"], "license": DATA_LICENSE,
            }
        if not a.get("eoNumber") and not alt.get("snapshot_url"):
            out[a["source_ref"]] = out.get(a["source_ref"]) or {
                "id": a["source_ref"], "title": a["title"], "url": "",
                "retrieved_at": a.get("verified_at") or d["meta"]["data_date"], "license": DATA_LICENSE,
            }
    out["openpalliative"] = {"id": "openpalliative", "title": "Разметка проекта openpalliative",
                             "url": "https://github.com/openpalliative/pal-norms",
                             "retrieved_at": d["meta"]["data_date"], "license": "CC BY 4.0"}
    return out


def build(name: str, items: list[dict], srcs: dict, meta: dict, root: Path) -> dict:
    sch = item_schema(root, name)
    clean = [coerce(it, sch) for it in items]
    if name == "entrypoints":
        clean = [{k: v for k, v in it.items() if k in sch["properties"]} for it in clean]
    else:
        clean = [{k: v for k, v in it.items() if k in sch["properties"] or k.startswith("_")} for it in clean]
    refs = {it.get("source_ref") for it in clean if it.get("source_ref")}
    source = [srcs[r] for r in sorted(refs) if r in srcs] or [srcs["openpalliative"]]
    return make_envelope(dataset=name, repo=REPO, items=clean, source=source, meta=meta,
                         schema_version=SCHEMA_VERSIONS.get(name, "1.0.0"))


def datasets(root: Path = ROOT) -> list[dict]:
    if os.environ.get("PN_FIXTURES") == "1":
        return fixtures(root)
    d = raw(root)
    derive(d, root)
    srcs = sources(d)
    out = [build(name, d[name], srcs, d["meta"], root) for name in NAMES]
    add_regional(next(e for e in out if e["dataset"] == "calendar"), root)
    return out


def add_regional(env: dict, root: Path) -> None:
    sch = schema(root, "calendar")["properties"]["regional"]["items"]
    rows = [coerce(r, sch) for r in regional.load(root)]
    env["regional"] = rows
    for r in rows:
        src = r["source_ref"]
        if src not in {s["id"] for s in env["source"]}:
            env["source"].append({"id": src, "title": f"{r['act']['number']}: {r['act']['title']}", "url": r["act"]["url"],
                                  "eoNumber": r["eoNumber"], "retrieved_at": r["verified_at"] or env["data_date"],
                                  "license": DATA_LICENSE})
    env["content_sha256"] = content_sha256(env["source"], env["items"])
