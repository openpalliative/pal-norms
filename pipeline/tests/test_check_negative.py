import yaml

from pipeline import check
from pipeline.io import dump_yaml, read_yaml


def edit(root, rel, fn):
    path = root / rel
    data = read_yaml(path)
    fn(data)
    dump_yaml(data, path)


def acts_by(data):
    return {a["id"]: a for a in data["acts"]}


def test_broken_symmetry(tmp_root):
    edit(tmp_root, "data/acts.yaml", lambda d: acts_by(d)["398n"].__setitem__("supersedes", []))
    assert any("не симметрична" in e for e in check.run(tmp_root))


def test_verified_quote_without_crop(tmp_root):
    (tmp_root / "raw" / "crops" / "208n-243n-p23.png").unlink()
    assert any("нет вырезки raw/crops/208n-243n-p23.png" in e for e in check.run(tmp_root))


def test_rule_value_must_be_in_quote(tmp_root):
    def bump(d):
        next(r for r in d["rules"] if r["id"] == "505n-transfer")["value"] = "6"
    edit(tmp_root, "data/deadline-rules.yaml", bump)
    assert any("505n-transfer: числа 6 нет" in e for e in check.run(tmp_root))


def test_verified_rule_needs_verified_quotes(tmp_root):
    def unverify(d):
        q = next(q for q in d["quotes"] if q["id"] == "180n-p16")
        q["verified"] = "false"
    edit(tmp_root, "data/quotes/180n.yaml", unverify)
    errors = check.run(tmp_root)
    assert any("180n-protocol-extract: правило проверено, а цитаты нет" in e for e in errors)


def test_ips_quote_cannot_be_verified(tmp_root):
    def verify(d):
        q = d["quotes"][0]
        q["verified"] = "true"
        q["verified_at"] = "2026-10-11"
    edit(tmp_root, "data/quotes/59-fz.yaml", verify)
    assert any("только цитата из официального PDF" in e for e in check.run(tmp_root))


def test_repealed_needs_lint_rule(tmp_root):
    edit(tmp_root, "data/lint-rules.yaml", lambda d: d.__setitem__("rules", [r for r in d["rules"] if r["id"] != "lint-348n"]))
    assert any("acts/348n: у отменённого акта с aliases нет правила" in e for e in check.run(tmp_root))


def test_excluded_territory_is_caught(tmp_root):
    def add(d):
        d["changes"][0]["summary"] += ", в том числе в Донецке"
    edit(tmp_root, "data/changes.yaml", add)
    assert any("исключённую территорию" in e for e in check.run(tmp_root))


def test_drug_name_is_caught(tmp_root):
    def add(d):
        d["rules"][0]["situation"] += " морфин"
    edit(tmp_root, "data/deadline-rules.yaml", add)
    assert any("название препарата" in e for e in check.run(tmp_root))


def test_unknown_reference(tmp_root):
    def add(d):
        d["steps"][0]["quote_ids"].append("no-such-quote")
    edit(tmp_root, "data/escalation.yaml", add)
    assert any("неизвестная цитата no-such-quote" in e for e in check.run(tmp_root))


def test_lint_pattern_dialect(tmp_root):
    def add(d):
        d["rules"][0]["patterns"].append("\\b345н\\b")
    edit(tmp_root, "data/lint-rules.yaml", add)
    assert any("не работают одинаково" in e for e in check.run(tmp_root))


def test_schema_errors_are_reported(tmp_root):
    def bad(d):
        acts_by(d)["180n"]["eoNumber"] = "123"
    edit(tmp_root, "data/acts.yaml", bad)
    errors = check.run(tmp_root)
    assert any("eoNumber" in e for e in errors)


def test_yaml_is_read_as_strings(tmp_root):
    raw = yaml.load((tmp_root / "data" / "acts.yaml").read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    assert raw["acts"][0]["verified"] == "true"
