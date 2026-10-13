import re
from pathlib import Path

import yaml

from pipeline.tests.conftest import ROOT

DATA = ROOT / "data"
MONTHS = "января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря"
REF = re.compile(rf"от\s+(\d{{1,2}})\s+({MONTHS})\s+(\d{{4}})\s*(?:г\.|года)?\s*№\s*(\d+)\s*(?:-\s*)?([а-яА-Я]*)")


def items(envs, name):
    return {i["id"]: i for i in envs[name]["items"]}


def test_repeal_in_changes_has_basis(envs):
    acts = items(envs, "acts")
    for c in envs["changes"]["items"]:
        if "утратил" not in c["summary"].lower():
            continue
        repealed = [acts[a] for a in c["related_act_ids"] if acts[a]["status"] == "repealed"]
        assert repealed, c["id"]
        for a in repealed:
            assert (a["status_basis"] or {}).get("quote_id"), a["id"]


def test_no_em_dash_in_data():
    for path in sorted(DATA.rglob("*.yaml")):
        assert "—" not in path.read_text(encoding="utf-8"), path.name


def test_no_em_dash_in_texts(envs):
    for q in envs["quotes"]["items"]:
        assert "—" not in q["text"], q["id"]
    for r in envs["indications"]["items"]:
        assert "—" not in r["text"], r["id"]


def test_indication_page_matches_quote(envs):
    quotes = items(envs, "quotes")
    for r in envs["indications"]["items"]:
        m = re.fullmatch(r"прил\. 1, п\. (\d+)", r["point"])
        if not m:
            continue
        q = quotes[f"208n-243n-a1-p{m.group(1)}"]
        last = q["page"] + len((q.get("scan_checked") or {}).get("crops") or [1]) - 1
        assert q["page"] <= r["page"] <= last, r["id"]
    p10 = [r for r in envs["indications"]["items"] if r["point"] == "прил. 1, п. 10"]
    assert p10 and {r["page"] for r in p10} == {12} == {quotes["208n-243n-a1-p10"]["page"]}


def _walk_eo(obj, path, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if "eonumber" in k.lower() and v is not None:
                out.append((path + "." + k, v))
            _walk_eo(v, path + "." + k, out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _walk_eo(v, f"{path}[{i}]", out)


def test_eo_numbers_are_strings_for_safe_load():
    for path in sorted(DATA.rglob("*.yaml")):
        found: list = []
        _walk_eo(yaml.safe_load(path.read_text(encoding="utf-8")), path.name, found)
        for where, value in found:
            assert isinstance(value, str) and re.fullmatch(r"\d{16}", value), where


def _known_refs():
    acts = yaml.safe_load((DATA / "acts.yaml").read_text(encoding="utf-8"))["acts"]
    cands = yaml.safe_load((DATA / "candidates.yaml").read_text(encoding="utf-8"))
    known = set()
    for a in acts:
        if a.get("number") and a.get("doc_date"):
            for n in re.split(r"[/]", str(a["number"])):
                known.add((str(a["doc_date"]), re.sub(r"[^0-9а-яa-z]", "", n.lower())))
        for m in a.get("amended_by") or []:
            num = re.search(r"№\s*(\d+\s*-?\s*[а-яА-Я]*)", m["title"])
            if num:
                known.add((str(m["doc_date"]), re.sub(r"[^0-9а-яa-z]", "", num.group(1).lower())))
    for c in cands.get("acts") or []:
        if c.get("doc_date") and c.get("number"):
            known.add((str(c["doc_date"]), re.sub(r"[^0-9а-яa-z]", "", str(c["number"]).lower())))
    return known


def test_every_act_named_in_quotes_is_known(envs):
    months = MONTHS.split("|")
    known = _known_refs()
    missing = []
    for q in envs["quotes"]["items"]:
        for m in REF.finditer(q["text"]):
            date = f"{m.group(3)}-{months.index(m.group(2)) + 1:02d}-{int(m.group(1)):02d}"
            num = re.sub(r"[^0-9а-яa-z]", "", (m.group(4) + m.group(5)).lower())
            if (date, num) not in known:
                missing.append((q["id"], date, num))
    assert missing == []


def test_cites_have_quotes(envs):
    acts = items(envs, "acts")
    for need, cited in (("208n-243n", "442-fz"), ("18-fz", "323-fz"), ("489-fz", "323-fz"), ("692n", "792n"),
                        ("398n", "323-fz")):
        c = [x for x in acts[need]["cites"] if x["act_id"] == cited]
        assert c and c[0]["quote_id"], (need, cited)


def test_repealed_acts_have_aliases(envs):
    for a in envs["acts"]["items"]:
        if a["status"] == "repealed":
            assert a["aliases"] or "без псевдонимов" in (a["notes"] or ""), a["id"]


def test_escalation_steps_have_basis_or_interpretation(envs):
    for s in envs["escalation"]["items"]:
        assert s["quote_ids"] or s.get("interpretation") is True, s["id"]
        if s.get("interpretation") is True:
            assert s.get("interpretation_note"), s["id"]


def test_amended_text_quotes_name_edition(envs):
    for q in envs["quotes"]["items"]:
        if q["id"].startswith(("gk-", "323fz-", "koap-")):
            assert q.get("edition"), q["id"]
            assert "редакции" in q["edition"] or "редакция" in q["edition"], q["id"]


def test_neighbour_quotes_exist(envs):
    quotes = items(envs, "quotes")
    for qid in ("398n-p1", "398n-fn1", "398n-fn2", "323fz-37-15", "789n-p2", "gk-185-1-p3", "gk-188-p1", "gk-1174-p3",
                "1094n-a1-p3", "208n-243n-p18", "323fz-22-3"):
        assert qid in quotes and quotes[qid]["verified"] is True, qid


def test_388n_status_from_424n(envs):
    a = items(envs, "acts")["388n"]
    assert a["status"] == "in_force" and a["status_basis"]["quote_id"] == "424n-o1"


def test_who_does_not_name_organization_for_p23(envs):
    r = items(envs, "deadline-rules")["208n-p23-transition"]
    assert r["who"].startswith("в пункте не сказано")


def test_amendments_scan_report_exists():
    rows = (ROOT / "raw" / "ocr-diff" / "323fz-amendments.tsv").read_text(encoding="utf-8").splitlines()
    assert rows[0].startswith("eoNumber\t") and len(rows) > 40


def test_sources_have_sha256_for_quoted_pdfs(envs):
    tsv = (ROOT / "raw" / "SOURCES.tsv").read_text(encoding="utf-8")
    acts = items(envs, "acts")
    for a in acts.values():
        if a["text_source"] == "official_pdf" and a["quote_ids"]:
            assert a["eoNumber"] + "\t" in tsv, a["id"]
            assert Path(ROOT / "raw" / "meta" / f"{a['eoNumber']}.json").is_file(), a["id"]


def test_second_check_for_every_verified_text(envs):
    for name in ("quotes", "indications"):
        for q in envs[name]["items"]:
            if not q["verified"] or q["text_source"] != "official_pdf":
                continue
            second = (q.get("scan_checked") or {}).get("second") or {}
            assert second.get("at") and second.get("method") and second.get("agrees") is True, (name, q["id"])


def test_quotes_on_two_pages_list_all_crops(envs):
    quotes = items(envs, "quotes")
    for qid in ("208n-243n-p4", "208n-243n-a1-p4", "208n-243n-a1-p8", "208n-243n-a1-p11", "208n-243n-a38-p9"):
        crops = quotes[qid]["scan_checked"]["crops"]
        assert len(crops) >= 2 and all((ROOT / "raw" / "crops" / c).is_file() for c in crops), qid


def test_candidates_say_where_and_why():
    cands = yaml.safe_load((DATA / "candidates.yaml").read_text(encoding="utf-8"))
    for row in cands["rules"] + cands["acts"]:
        assert row.get("id") and row.get("what") and row.get("why_not_published"), row
    for row in cands["rules"]:
        assert row.get("where"), row["id"]


def test_calendar_decrees_link_their_quotes(envs):
    acts = items(envs, "acts")
    for y in envs["calendar"]["items"]:
        if y["kind"] == "year":
            assert set(y["quote_ids"]) <= set(acts[y["decree_act_id"]]["quote_ids"]), y["id"]


def test_nutrition_list_amendments(envs):
    amended = {m["eoNumber"] for m in items(envs, "acts")["3551-r-2023"]["amended_by"]}
    assert {"0001202409190039", "0001202501270007", "0001202511100019"} <= amended


def test_tk_112_amendments_searched():
    rows = (ROOT / "raw" / "ocr-diff" / "tk-amendments.tsv").read_text(encoding="utf-8").splitlines()
    head = rows[0].split("\t")
    assert head[:4] == ["eoNumber", "number", "doc_date", "pages"] and len(rows) > 60
    col = head.index("st112")
    assert all(r.split("\t")[col] == "0" for r in rows[1:])
