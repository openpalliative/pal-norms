import datetime as dt
from pathlib import Path

from .io import ROOT, read_yaml


def _d(iso: str) -> dt.date:
    return dt.date.fromisoformat(iso)


def holiday_dates(year: int, mmdd: list[str]) -> list[dt.date]:
    return [dt.date(year, int(m[:2]), int(m[3:])) for m in mmdd]


def year_days(year: int, baseline: dict, transfers: list[dict]) -> tuple[list[str], list[str]]:
    holidays = set(holiday_dates(year, baseline["holidays_mmdd"]))
    excluded = set(holiday_dates(year, baseline.get("carry_exclude_mmdd") or []))
    moved_from = {_d(t["from"]) for t in transfers}
    off = set(holidays) | {_d(t["to"]) for t in transfers}
    work = {d for d in moved_from if d not in holidays and d.weekday() >= 5}
    if baseline.get("carry_over") in (True, "true"):
        for h in sorted(holidays - excluded):
            if h.weekday() < 5 or h in moved_from:
                continue
            d = h + dt.timedelta(days=1)
            while d.weekday() >= 5 or d in off:
                d += dt.timedelta(days=1)
            off.add(d)
    return sorted(d.isoformat() for d in off), sorted(d.isoformat() for d in work)


def load(root: Path = ROOT) -> tuple[dict, list[dict]]:
    base = read_yaml(root / "data" / "calendar" / "holidays.yaml")["baseline"]
    years = read_yaml(root / "data" / "calendar" / "transfers.yaml")["years"]
    return base, years


def items(root: Path = ROOT) -> list[dict]:
    base, years = load(root)
    out = [{
        "id": "baseline", "verified": base["verified"], "verified_at": base["verified_at"],
        "source_ref": base["source_ref"], "kind": "baseline", "year": None,
        "holidays_mmdd": base["holidays_mmdd"], "carry_over": base["carry_over"],
        "carry_exclude_mmdd": base["carry_exclude_mmdd"], "quote_ids": base["quote_ids"],
    }]
    for y in years:
        year = int(y["year"])
        transfers = [{"from": t["from"], "to": t["to"]} for t in y.get("transfers") or []]
        off, work = year_days(year, base, transfers)
        verified = y["verified"] == "true" and base["verified"] == "true"
        out.append({
            "id": str(year), "verified": "true" if verified else "false",
            "verified_at": y["verified_at"] if verified else "", "source_ref": y["source_ref"], "kind": "year",
            "year": str(year), "decree_act_id": y["decree_act_id"], "decree_eoNumber": y["decree_eoNumber"],
            "transfers": transfers, "off": off, "work": work, "quote_ids": y["quote_ids"],
        })
    return out
