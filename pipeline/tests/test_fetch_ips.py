from pipeline import fetch_ips
from pipeline.io import read_yaml
from pipeline.tests.conftest import ROOT

SNAPSHOT = ROOT / "raw" / "ips" / "59-fz-20260626091943.html"


def paras():
    return fetch_ips.paragraphs(fetch_ips.decode(SNAPSHOT.read_bytes()))


def test_snapshot_is_cp1251_and_has_latest_edition():
    eds = fetch_ips.editions(fetch_ips.decode(SNAPSHOT.read_bytes()))
    assert ("28.12.2024", "547-ФЗ") in eds


def test_parts_match_stored_quotes():
    quotes = {q["id"]: q for q in read_yaml(ROOT / "data" / "quotes" / "59-fz.yaml")["quotes"]}
    p = paras()
    assert fetch_ips.part(p, "12", "1") == quotes["59-fz-s12-1"]["text"]
    assert fetch_ips.part(p, "8", "2") == quotes["59-fz-s8-2"]["text"]
    assert fetch_ips.item(p, "10", "1", "4") == quotes["59-fz-s10-1"]["text"]


def test_superscript_and_notes():
    text = fetch_ips.part(paras(), "12", "1")
    assert "части 1¹ настоящей статьи" in text
    assert "В редакции" not in text
