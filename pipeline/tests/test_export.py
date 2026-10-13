import os

from pipeline import export
from pipeline.tests.conftest import ROOT


def test_all_datasets_built(envs):
    assert set(envs) == set(export.NAMES)
    for env in envs.values():
        assert env["repo"] == "pal-norms"
        assert env["counts"]["items"] == len(env["items"])
        assert env["counts"]["excluded"] == 0


def test_content_hash_is_stable():
    a = {e["dataset"]: e["content_sha256"] for e in export.datasets(ROOT)}
    b = {e["dataset"]: e["content_sha256"] for e in export.datasets(ROOT)}
    assert a == b


def test_fixture_mode(monkeypatch):
    monkeypatch.setenv("PN_FIXTURES", "1")
    envs = export.datasets(ROOT)
    assert envs and all(i["id"].startswith("demo-") for e in envs if e["dataset"] != "calendar" for i in e["items"])


def test_sources_have_official_urls(envs):
    for src in envs["acts"]["source"]:
        if src.get("eoNumber"):
            assert src["url"] == f"http://publication.pravo.gov.ru/document/{src['eoNumber']}"


def test_entrypoints_match_architecture(envs):
    ids = [e["id"] for e in envs["entrypoints"]["items"]]
    assert ids == ["deadlines", "escalation", "indications", "calendar", "acts", "check", "changes", "data"]
    assert os.environ.get("PN_FIXTURES") != "1"
