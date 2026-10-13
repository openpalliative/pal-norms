import json
import re

import pytest

from pipeline import regional
from pipeline.pravo import DENY_BLOCKS, Client, Transport
from pipeline.tests.conftest import ROOT

EXCLUDED = re.compile(r"^RU-(DON|LUG|ZAP|KHE|CR|SEV)$")


class Fake(Transport):
    def __init__(self):
        self.calls = []

    def get(self, path, params=None):
        self.calls.append((path, dict(params or {})))
        if path == "/api/PublicBlocks":
            return json.dumps([{"code": c, "shortName": c} for c in ("region16", *sorted(DENY_BLOCKS), "region03")]).encode()
        if path == "/api/Documents":
            return json.dumps({"items": [], "itemsTotalCount": 0, "currentPage": 1, "pagesTotalCount": 0}).encode()
        raise AssertionError(path)


def test_search_never_asks_denied_blocks():
    fake = Fake()
    regional.search(Client(fake), "01.06.2025", terms=("Курбан",))
    asked = {p.get("Block") for path, p in fake.calls if path == "/api/Documents"}
    assert asked == {"region16", "region03"}


@pytest.mark.parametrize("block", sorted(DENY_BLOCKS))
def test_client_refuses_denied_block_and_documents(block):
    fake = Fake()
    with pytest.raises(ValueError):
        Client(fake).search(30, 1, Name="праздничных", Block=block)
    with pytest.raises(ValueError):
        Client(fake).pdf(block[-2:] + "00202601010001")
    with pytest.raises(ValueError):
        Client(fake).document_raw(block[-2:] + "00202601010001")
    assert fake.calls == []


def test_regional_rows_are_clean():
    rows = regional.load(ROOT)
    assert rows
    regions_2026 = {r["region_id"] for r in rows if r["date"].startswith("2026")}
    assert len(regions_2026) >= 14
    for r in rows:
        assert not EXCLUDED.match(r["region_id"]), r["id"]
        assert r["date"][:4] in ("2026", "2027"), r["id"]
        assert r["act"]["eoNumber"] == r["eoNumber"] and not r["eoNumber"].startswith(tuple(b[-2:] for b in DENY_BLOCKS))
        assert r["quote_ids"] == [r["quote"]["id"]]
        sc = r["quote"]["scan_checked"]
        for crop in sc["crops"]:
            assert (ROOT / "raw" / "crops" / crop).is_file(), crop
        assert r["legal_review"]["status"] == "none"
        if r["verified"] == "true":
            assert sc["second"]["agrees"] == "true", r["id"]


def test_regional_is_published_apart_from_calendar(envs):
    cal = envs["calendar"]
    assert cal["regional"] and all(i["kind"] in ("baseline", "year") for i in cal["items"])
    assert all(isinstance(r["verified"], bool) for r in cal["regional"])
