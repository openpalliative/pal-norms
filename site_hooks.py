import datetime as dt
import json
import os
import re
from xml.sax.saxutils import escape
from itertools import groupby

MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
              "августа", "сентября", "октября", "ноября", "декабря"]
SUNSET_DAYS = 120


def _items(ctx, name: str) -> list:
    env = ctx.data.get(name)
    return env["items"] if env else []


def _plural(n: int, forms: list) -> str:
    m10, m100 = n % 10, n % 100
    if m10 == 1 and m100 != 11:
        return forms[0]
    if 2 <= m10 <= 4 and not 12 <= m100 <= 14:
        return forms[1]
    return forms[2]


def _amount(value: int, unit: str, labels: dict) -> str:
    if unit == "within_24h":
        return "сутки" if value == 1 else f"{value} {_plural(value, labels['units'][unit])}"
    return f"{value} {_plural(value, labels['units'][unit])}"


def rule_terms(rule: dict, labels: dict) -> dict:
    main = _amount(rule["value"], rule["unit"], labels)
    if rule["unit"] == "within_24h":
        headline = "В течение суток" if rule["value"] == 1 else f"В течение {main}"
    elif rule["direction"] == "backward":
        headline = f"Не позднее чем за {main}"
    else:
        headline = main
    pre = rule.get("pre")
    ext = rule.get("extension")
    shift = {"yes": "переносится на ближайший рабочий день",
             "no": "не переносится",
             "unknown": "в норме не сказано, поэтому показываем обе даты"}[rule["shift_if_nonworking"]]
    return {
        "headline": headline,
        "pre": f"{_amount(pre['value'], pre['unit'], labels)} {pre['label']}" if pre else "",
        "extension": f"{_amount(ext['value'], ext['unit'], labels)}, {ext['label']}" if ext else "",
        "shift": shift,
        "summary": headline + (f", плюс {_amount(pre['value'], pre['unit'], labels)} {pre['label']}" if pre else ""),
    }


def _date(s):
    return dt.date.fromisoformat(s) if s else None


def day_long(d: dt.date, labels: dict) -> str:
    return f"{d.day} {MONTHS_GEN[d.month - 1]}"


def _span_text(a: dt.date, b: dt.date) -> str:
    if a == b:
        return f"{a.day} {MONTHS_GEN[a.month - 1]}"
    if a.month == b.month:
        return f"{a.day}-{b.day} {MONTHS_GEN[a.month - 1]}"
    return f"с {a.day} {MONTHS_GEN[a.month - 1]} по {b.day} {MONTHS_GEN[b.month - 1]}"


def year_view(item: dict, labels: dict) -> dict:
    year = item["year"]
    off = {_date(d) for d in item.get("off") or []}
    work = {_date(d) for d in item.get("work") or []}
    start, end = dt.date(year, 1, 1), dt.date(year, 12, 31)

    def resting(d):
        return d in off or (d.weekday() >= 5 and d not in work)

    ranges = []
    d = start
    while d <= end:
        if resting(d):
            a = d
            while d + dt.timedelta(days=1) <= end and resting(d + dt.timedelta(days=1)):
                d += dt.timedelta(days=1)
            if any(x in off for x in (a + dt.timedelta(days=i) for i in range((d - a).days + 1))):
                n = (d - a).days + 1
                ranges.append({"start": a.isoformat(), "end": d.isoformat(), "text": _span_text(a, d),
                               "days": n, "days_text": f"{n} {_plural(n, ['день', 'дня', 'дней'])}",
                               "month": a.month})
        d += dt.timedelta(days=1)
    wd = labels["weekdays"]
    wdf = labels["weekdays_from"]
    transfers = []
    for t in item.get("transfers") or []:
        a, b = _date(t["from"]), _date(t["to"])
        transfers.append({"from": t["from"], "to": t["to"],
                          "text": f"Выходной переносится с {wdf[a.weekday()]} {day_long(a, labels)} "
                                  f"на {labels['weekdays_to'][b.weekday()]} {day_long(b, labels)}"
                                  + (f" {b.year} года" if b.year != a.year else "")})
    work_days = [{"date": x.isoformat(), "text": f"{wd[x.weekday()]} {day_long(x, labels)}"} for x in sorted(work)]
    months = []
    for m, group in groupby(sorted(ranges, key=lambda r: r["month"]), key=lambda r: r["month"]):
        months.append({"month": labels["months"][m - 1], "ranges": list(group)})
    total_off = sum(1 for i in range((end - start).days + 1) if resting(start + dt.timedelta(days=i)))
    return {"year": year, "id": item["id"], "verified": item["verified"], "verified_at": item["verified_at"],
            "decree_act_id": item.get("decree_act_id"), "decree_eoNumber": item.get("decree_eoNumber"),
            "quote_ids": item.get("quote_ids") or [], "ranges": ranges, "months": months,
            "transfers": transfers, "work_days": work_days, "approved": bool(item.get("decree_act_id")),
            "nonworking_total": total_off}


def baseline_year(baseline: dict, year: int) -> dict:
    hol = {dt.date.fromisoformat(f"{year}-{md}") for md in baseline.get("holidays_mmdd") or []}
    off = set(hol)
    if baseline.get("carry_over"):
        skip = set(baseline.get("carry_exclude_mmdd") or [])
        for d in sorted(hol):
            if d.weekday() < 5 or d.strftime("%m-%d") in skip:
                continue
            n = d + dt.timedelta(days=1)
            while n.weekday() >= 5 or n in off:
                n += dt.timedelta(days=1)
            if n.year == year:
                off.add(n)
    return {"id": str(year), "year": year, "verified": False, "verified_at": None,
            "off": [d.isoformat() for d in sorted(off)], "work": [], "transfers": [],
            "quote_ids": list(baseline.get("quote_ids") or []), "decree_act_id": None, "decree_eoNumber": None}


def upcoming_ranges(years: list) -> list:
    out = []
    for y in years:
        for r in y["ranges"]:
            a, b = _date(r["start"]), _date(r["end"])
            if out and _date(out[-1]["end"]) + dt.timedelta(days=1) == a:
                out[-1]["end"] = r["end"]
                out[-1]["approved"] = out[-1]["approved"] and y["approved"]
                out[-1]["unapproved_years"] += [] if y["approved"] else [y["year"]]
            else:
                out.append({"start": r["start"], "end": r["end"], "approved": y["approved"],
                            "unapproved_years": [] if y["approved"] else [y["year"]]})
    for r in out:
        a, b = _date(r["start"]), _date(r["end"])
        if a.year == b.year:
            r["text"] = f"{_span_text(a, b)} {a.year}"
        else:
            r["text"] = f"с {a.day} {MONTHS_GEN[a.month - 1]} {a.year} по {b.day} {MONTHS_GEN[b.month - 1]} {b.year}"
        n = (b - a).days + 1
        r["days_text"] = "1 день" if n == 1 else f"{n} {_plural(n, ['день', 'дня', 'дней'])} подряд"
    return out


def _rule_group(rule: dict, acts: dict, groups: list) -> str:
    if rule.get("group") in {g["id"] for g in groups}:
        return rule["group"]
    for g in groups:
        if rule["from_event"] in (g.get("events") or []):
            return g["id"]
    topics = []
    for nid in rule["norm_ids"]:
        topics += (acts.get(nid) or {}).get("topics") or []
    for g in groups:
        if set(g.get("topics") or []) & set(topics):
            return g["id"]
    return "other"


def indications_view(rows: list) -> dict:
    out = {}
    for aud in ("adults", "children"):
        part = sorted((r for r in rows if r["audience"] == aud), key=lambda r: r["order"])
        groups = []
        for r in part:
            if r["section"] != "group":
                continue
            if not groups or groups[-1]["id"] != r["group_id"]:
                groups.append({"id": r["group_id"], "title": r["group_title"] or "", "rows": []})
            groups[-1]["rows"].append(r)
        out[aud] = {"scope": [r for r in part if r["section"] == "scope"],
                    "rule": [r for r in part if r["section"] == "rule"],
                    "general": [r for r in part if r["section"] == "general"],
                    "groups": groups,
                    "decision": [r for r in part if r["section"] == "decision"],
                    "count": len(part),
                    "unverified": sum(1 for r in part if not r["verified"])}
    return out


def _watch_state(root) -> dict | None:
    p = root / "data" / "snapshots" / "watch-state.json"
    if not p.is_file():
        return None
    try:
        state = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return {"checked_at": (state.get("checked_at") or "")[:10] or None,
            "last_ok_at": (state.get("last_ok_at") or "")[:10] or None,
            "failures": int(state.get("consecutive_failures") or 0)}


def context(ctx) -> dict:
    labels = ctx.content.get("labels", {})
    gates = ctx.content.get("gates", {})
    acts = _items(ctx, "acts")
    acts_by_id = {a["id"]: a for a in acts}
    snapshot_dates = {}
    for a in acts:
        m = re.search(r"/web/(\d{4})(\d{2})(\d{2})", ((a.get("alt_source") or {}).get("snapshot_url") or ""))
        if m:
            snapshot_dates[a["id"]] = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    quotes_by_id = {q["id"]: q for q in _items(ctx, "quotes")}
    rules = _items(ctx, "deadline-rules")
    groups = labels.get("rule_groups", [])
    rule_view = []
    for r in rules:
        rule_view.append({"rule": r, "terms": rule_terms(r, labels), "group": _rule_group(r, acts_by_id, groups)})
    rule_groups = []
    for g in groups:
        members = [rv for rv in rule_view if rv["group"] == g["id"]]
        if members:
            rule_groups.append({"id": g["id"], "title": g["title"], "rules": members})
    esc = sorted(_items(ctx, "escalation"), key=lambda e: e["order"])
    cal = _items(ctx, "calendar")
    baseline = next((c for c in cal if c["kind"] == "baseline"), None)
    years = sorted((year_view(c, labels) for c in cal if c["kind"] == "year"), key=lambda y: y["year"])
    if baseline and years:
        stub = year_view(baseline_year(baseline, years[-1]["year"] + 1), labels)
        stub["stub"] = True
        years.append(stub)
    changes = sorted(_items(ctx, "changes"), key=lambda c: (c["published_at"], c["id"]), reverse=True)

    any_env = next(iter(ctx.data.values()), None)
    data_date = any_env["data_date"] if any_env else None
    stale = any_env["stale_after_days"] if any_env else 90
    built = dt.date.fromisoformat(ctx.built_at[:10])
    sheet_until = (_date(data_date) + dt.timedelta(days=stale)).isoformat() if data_date else None

    topic_titles = {}
    for t in labels.get("topics", []):
        topic_titles.setdefault(t["title"], []).append(t["id"])
    act_groups = []
    placed = set()
    for title, ids in topic_titles.items():
        members = [a for a in acts if a["id"] not in placed and set(a.get("topics") or []) & set(ids)]
        members.sort(key=lambda a: (a["status"] == "repealed", a["short_title"]))
        placed |= {a["id"] for a in members}
        if members:
            act_groups.append({"title": title, "acts": members})
    rest = [a for a in acts if a["id"] not in placed]
    if rest:
        act_groups.append({"title": "Другое", "acts": rest})

    sunset = {}
    for a in acts:
        vu = _date(a.get("valid_until"))
        if vu and a["status"] == "in_force" and 0 <= (vu - built).days <= SUNSET_DAYS:
            sunset[a["id"]] = vu.isoformat()

    situations = [s for s in (ctx.situations or [])]
    target = os.environ.get("OP_TARGET", "")
    indications_public = gates.get("indications_public") in (True, "true")
    datasets = []
    for name, env in sorted(ctx.data.items()):
        datasets.append({"name": name, "summary": labels.get("datasets", {}).get(name, ""),
                         "items": env["counts"]["items"], "unverified": env["counts"]["unverified"],
                         "version": env["version"], "schema_version": env["schema_version"],
                         "data_date": env["data_date"]})
    qs = list(quotes_by_id.values())
    unv_q = [q for q in qs if not q["verified"]]
    ips_acts = []
    for q in unv_q:
        if q["text_source"] == "ips_archive" and q["act_id"] not in ips_acts:
            ips_acts.append(q["act_id"])
    counts = {
        "quotes_scan": sum(1 for q in qs if q["verified"] and q["text_source"] == "official_pdf"),
        "quotes_unverified": len(unv_q),
        "quotes_ips": sum(1 for q in unv_q if q["text_source"] == "ips_archive"),
        "quotes_ips_acts": ips_acts,
        "acts": len(acts),
        "acts_verified": sum(1 for a in acts if a["verified"]),
        "rules": len(rules),
        "quotes": len(quotes_by_id),
        "years": [y["year"] for y in years],
    }
    ind_rows = _items(ctx, "indications")
    ind_anchor = {}
    for r in sorted(ind_rows, key=lambda r: (r["audience"], r["order"])):
        ind_anchor.setdefault((r["act_id"], r["anchor"]), r["id"])
    return {"pn": {
        "labels": labels,
        "acts": acts, "acts_by_id": acts_by_id, "act_groups": act_groups,
        "quotes": quotes_by_id, "snapshot_dates": snapshot_dates,
        "rules": rule_view, "rules_by_id": {rv["rule"]["id"]: rv for rv in rule_view}, "rule_groups": rule_groups,
        "escalation": esc, "esc_by_id": {e["id"]: e for e in esc},
        "esc_links": ctx.content.get("escalation-links", {}).get("triggers", {}),
        "indications": indications_view(ind_rows),
        "ind_anchor": {f"{k[0]}#{k[1]}": v for k, v in ind_anchor.items()},
        "indications_stub": target == "pages" and not indications_public,
        "baseline": baseline, "years": years, "upcoming": upcoming_ranges(years), "years_by_id": {str(y["year"]): y for y in years},
        "changes": changes,
        "lint_rules": _items(ctx, "lint-rules"),
        "watch": _watch_state(ctx.root),
        "data_date": data_date, "stale_after": stale, "sheet_until": sheet_until,
        "built": built.isoformat(), "sunset": sunset,
        "datasets": datasets, "counts": counts,
        "situations": situations,
        "home": ctx.content.get("home", {}),
    }}


def atom_feed(site: dict, changes: list, labels: dict, built_at: str) -> str:
    root = (os.environ.get("OP_SITE_URL") or site.get("site_url") or "https://openpalliative.github.io").rstrip("/")
    page = f"{root}{site['base']}changes/"
    updated = max((c["published_at"] for c in changes), default=built_at[:10])
    kinds = labels.get("change_kind", {})
    out = ['<?xml version="1.0" encoding="utf-8"?>',
           '<feed xmlns="http://www.w3.org/2005/Atom" xml:lang="ru">',
           f"<title>{escape(site['title'])}: что изменилось</title>",
           f"<subtitle>{escape('Новые и изменённые документы на портале официальной публикации, которые касаются паллиативной помощи')}</subtitle>",
           f'<link rel="alternate" type="text/html" href="{escape(page)}"/>',
           f'<link rel="self" type="application/atom+xml" href="{escape(page)}changes.xml"/>',
           f"<id>{escape(page)}</id>",
           f"<updated>{updated}T00:00:00Z</updated>",
           "<author><name>openpalliative</name></author>"]
    for c in changes:
        href = f"http://publication.pravo.gov.ru/document/{c['eoNumber']}" if c.get("eoNumber") else page
        title = f"{kinds.get(c['kind'], '')}: {c['title']}" if kinds.get(c["kind"]) else c["title"]
        out += ["<entry>",
                f"<title>{escape(title)}</title>",
                f'<link rel="alternate" type="text/html" href="{escape(href)}"/>',
                f"<id>{escape(page)}#{escape(c['id'])}</id>",
                f"<updated>{c['published_at']}T00:00:00Z</updated>",
                f"<summary>{escape(c.get('summary') or c['title'])}</summary>",
                "</entry>"]
    out.append("</feed>")
    return "\n".join(out) + "\n"


def pages(ctx):
    pn = ctx.site["pn"]
    feed = ctx.out / "changes" / "changes.xml"
    feed.parent.mkdir(parents=True, exist_ok=True)
    feed.write_text(atom_feed(ctx.site, pn["changes"], pn["labels"], ctx.built_at), encoding="utf-8")
    for act in pn["acts"]:
        yield f"acts/{act['id']}/", "pn/act.html.j2", {"act": act, "nav_current": "acts/"}
    for rv in pn["rules"]:
        yield f"deadlines/{rv['rule']['id']}/", "pn/deadline-rule.html.j2", {"rv": rv, "nav_current": "deadlines/"}
    for y in pn["years"]:
        yield f"calendar/{y['year']}/", "pn/calendar-year.html.j2", {"y": y}
