import datetime as dt
import os
import shutil
import subprocess
import sys

from pipeline import check, export
from pipeline.tests.conftest import ROOT

REVIEWS = """reviews:
- target_kind: rule
  target: 505n-transfer
  role: lawyer
  reviewed_at: 2025-01-10
  expires_after: 6m
  verdict: ok
  ref: https://github.com/openpalliative/pal-norms/pull/1
- target_kind: rule
  target: 505n-vk-decision
  role: lawyer
  reviewed_at: 2026-10-01
  expires_after: 1y
  verdict: ok
- target_kind: act
  target: 398n
  role: lawyer
  reviewed_at: 2026-09-01
  expires_after: 30
  verdict: ok
- target_kind: quote
  target: 505n-p4
  role: lawyer
  reviewed_at: 2026-10-01
  expires_after: 1y
  verdict: unsure
- target_kind: indication
  target: adults-p4-0
  role: medic
  reviewed_at: 2026-10-01
  expires_after: 1y
  verdict: ok
"""


def test_expires_at_units():
    assert export.expires_at("2026-01-31", "1m") == "2026-02-28"
    assert export.expires_at("2026-01-01", "1y") == "2027-01-01"
    assert export.expires_at("2026-01-01", "30") == "2026-01-31"
    assert export.expires_at("2026-01-01", "10d") == "2026-01-11"
    assert export.expires_at("", "1y") == ""


def test_review_status_by_date():
    r = {"verdict": "ok", "reviewed_at": "2026-01-01", "expires_after": "1y", "role": "lawyer"}
    assert export.review_status(r, dt.date(2026, 12, 31))["status"] == "ok"
    assert export.review_status(r, dt.date(2027, 1, 1))["status"] == "ok"
    assert export.review_status(r, dt.date(2027, 1, 2))["status"] == "expired"
    assert export.review_status({**r, "verdict": "wrong"}, dt.date(2026, 2, 1))["status"] == "none"


def test_reviews_bind_to_all_kinds(tmp_root, monkeypatch):
    (tmp_root / "data" / "review" / "fixture.yaml").write_text(REVIEWS, encoding="utf-8")
    monkeypatch.setenv("PN_TODAY", "2026-10-11")
    envs = {e["dataset"]: e for e in export.datasets(tmp_root)}
    rules = {r["id"]: r for r in envs["deadline-rules"]["items"]}
    assert rules["505n-transfer"]["legal_review"]["status"] == "expired"
    assert rules["505n-transfer"]["legal_review"]["expires_at"] == "2025-07-10"
    assert rules["505n-vk-decision"]["legal_review"]["status"] == "ok"
    assert {a["id"]: a for a in envs["acts"]["items"]}["398n"]["review"]["status"] == "expired"
    assert {q["id"]: q for q in envs["quotes"]["items"]}["505n-p4"]["review"]["status"] == "none"
    assert {i["id"]: i for i in envs["indications"]["items"]}["adults-p4-0"]["review"]["status"] == "ok"
    assert check.check_reviews(tmp_root, envs) == []


def test_review_schema_and_unknown_target(tmp_root):
    (tmp_root / "data" / "review" / "bad.yaml").write_text(
        "reviews:\n- target_kind: rule\n  target: nope\n  role: lawyer\n  reviewed_at: 2026-10-01\n"
        "  expires_after: 1y\n  verdict: ok\n- target_kind: rule\n  target: 505n-p4\n  role: judge\n"
        "  reviewed_at: 01.10.2026\n  expires_after: year\n  verdict: maybe\n", encoding="utf-8")
    envs = {e["dataset"]: e for e in export.datasets(tmp_root)}
    errors = check.check_reviews(tmp_root, envs)
    assert errors and all("bad.yaml" in e for e in errors)


def test_expired_review_on_page(tmp_path):
    site = tmp_path / "site"
    for part in ("data", "pipeline", "templates", "assets", "content", "lib", "opsite", "tests/fixtures"):
        if (ROOT / part).is_dir():
            shutil.copytree(ROOT / part, site / part, ignore=shutil.ignore_patterns("__pycache__", "tests"))
    for f in ("site.yaml", "site_hooks.py"):
        shutil.copy(ROOT / f, site / f)
    (site / "data" / "review" / "fixture.yaml").write_text(REVIEWS, encoding="utf-8")
    env = {**os.environ, "PN_TODAY": "2026-10-11"}
    env.pop("PN_FIXTURES", None)
    res = subprocess.run([sys.executable, "-m", "opsite", "build"], cwd=site, env=env, capture_output=True, text=True)
    assert res.returncode == 0, res.stdout + res.stderr
    expired = (site / "_site" / "deadlines" / "505n-transfer" / "index.html").read_text(encoding="utf-8")
    fresh = (site / "_site" / "deadlines" / "505n-vk-decision" / "index.html").read_text(encoding="utf-8")
    assert "Проверка юристом устарела" in expired
    assert "Проверка юристом устарела" not in fresh
    assert "Толкование проверил юрист в РФ" in fresh
