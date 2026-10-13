from pipeline import check
from pipeline.tests.conftest import ROOT


def test_validator_has_no_errors():
    assert check.run(ROOT) == []


def test_acceptance_counts(envs):
    acts = envs["acts"]["items"]
    assert sum(1 for a in acts if a["verified"] and a["eoNumber"]) >= 15
    assert sum(1 for r in envs["deadline-rules"]["items"] if r["verified"]) >= 6
    assert len(envs["lint-rules"]["items"]) >= 6
    law = next(a for a in acts if a["id"] == "59-fz")
    assert law["verified"] is False and law["text_source"] == "ips_archive"


def test_indications_cover_required_points(envs):
    rows = envs["indications"]["items"]
    points = {r["point"] for r in rows}
    for p in ("п. 4 Положения", "п. 5 Положения", "прил. 1, п. 1", "прил. 1, п. 2", "п. 12 Положения",
              "п. 13 Положения", "п. 15 Положения"):
        assert p in points
    groups = {r["group_id"] for r in rows if r["section"] == "group"}
    assert groups == {f"a1-p{n}" for n in range(3, 12)}
    assert sum(1 for r in rows if r["verified"]) / len(rows) >= 0.9
    assert {r["audience"] for r in rows} == {"adults", "children"}


def test_calendar_years_verified(envs):
    years = {i["id"]: i for i in envs["calendar"]["items"]}
    for y in ("2025", "2026", "2027"):
        assert years[y]["verified"] is True


def test_rule_values_in_quotes(envs):
    quotes = {q["id"]: q for q in envs["quotes"]["items"]}
    for r in envs["deadline-rules"]["items"]:
        text = " ".join(quotes[q]["text"] for q in r["quote_ids"])
        assert check.value_in_text(r["value"], text), r["id"]


def test_legal_review_not_claimed(envs):
    for r in envs["deadline-rules"]["items"] + envs["escalation"]["items"]:
        assert r["legal_review"]["status"] == "none"


def test_repealed_acts_point_to_replacement(envs):
    acts = {a["id"]: a for a in envs["acts"]["items"]}
    for a in acts.values():
        if a["status"] == "repealed":
            assert a["superseded_by"], a["id"]
    assert acts["208n-243n"]["cites_repealed"][0]["act_id"] == "348n"
    assert "208n-p23-transition" in acts["208n-243n"]["rule_ids"]


def test_no_synthetic_ids(envs):
    for env in envs.values():
        assert not any(str(i["id"]).startswith("demo-") for i in env["items"])
