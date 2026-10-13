import argparse
import json
import sys
from pathlib import Path

from opsite.data import BuildError, validate

from . import export
from .io import ROOT, dump_yaml, read_yaml

KEYS = ("target_kind", "target", "role", "reviewed_at", "expires_after", "expires_at", "verdict", "questions", "ref",
        "notes")


def normalize(raw: dict) -> dict:
    r = {k: raw.get(k) for k in KEYS if raw.get(k) not in (None, "")}
    qs = raw.get("questions") or {}
    if isinstance(qs, dict):
        qs = [{"id": k, "answer": str(v).strip()} for k, v in qs.items()]
    r["questions"] = [{k: v for k, v in q.items() if v not in (None, "")} for q in qs] if qs else []
    if not r["questions"]:
        del r["questions"]
    r["expires_at"] = export.expires_at(str(r.get("reviewed_at") or ""), str(r.get("expires_after") or "")) or None
    if r["expires_at"] is None:
        del r["expires_at"]
    return r


def ingest(root: Path, src: Path) -> Path:
    doc = read_yaml(src) or {}
    items = doc.get("reviews") if isinstance(doc, dict) and "reviews" in doc else [doc]
    reviews = [normalize(r) for r in items]
    sch = json.loads((root / "data" / "schema" / "review.schema.json").read_text(encoding="utf-8"))
    validate({"reviews": reviews}, sch, f"ревью {src.name}")
    envs = {e["dataset"]: e for e in export.datasets(root)}
    for r in reviews:
        name = export.TARGET_KINDS[r["target_kind"]]
        if r["target"] not in {it["id"] for it in envs[name]["items"]}:
            raise BuildError(f"ревью {src.name}: нет {r['target_kind']} {r['target']}")
    target = reviews[0]["target"]
    out = root / "data" / "review" / f"{target}.yaml"
    old = read_yaml(out)["reviews"] if out.is_file() else []
    key = lambda r: (r.get("target_kind"), r.get("target"), r.get("role"), r.get("reviewed_at"))
    merged = [r for r in old if key(r) not in {key(n) for n in reviews}] + reviews
    dump_yaml({"reviews": sorted(merged, key=lambda r: (r["target"], r["reviewed_at"]))}, out)
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="pipeline.review_ingest")
    p.add_argument("file", type=Path)
    a = p.parse_args(argv)
    try:
        out = ingest(ROOT, a.file)
    except (BuildError, LookupError, KeyError) as e:
        print(e, file=sys.stderr)
        return 1
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
