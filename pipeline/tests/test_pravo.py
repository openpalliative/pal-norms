import json

import pytest

from pipeline import pravo


def test_parse_meta_requires_keys():
    with pytest.raises(pravo.SourceFormatError):
        pravo.parse_meta({"eoNumber": "1"})


def test_parse_page_requires_items():
    with pytest.raises(pravo.SourceFormatError):
        pravo.parse_page({"items": None, "itemsTotalCount": 1})


class Fake(pravo.Transport):
    def __init__(self, body=b"{}"):
        self.body = body
        self.calls = []

    def get(self, path, params=None):
        self.calls.append((path, params))
        return self.body


def test_page_size_and_block_guard():
    c = pravo.Client(Fake())
    with pytest.raises(ValueError):
        c.search(page_size=25, Name="x")
    with pytest.raises(ValueError):
        c.search(Name="x", Block="subjects")


def test_non_json_is_format_error():
    with pytest.raises(pravo.SourceFormatError):
        pravo.Client(Fake(b"<html>")).search(Name="x")


def test_pdf_must_be_pdf():
    with pytest.raises(pravo.SourceFormatError):
        pravo.Client(Fake(b"<html>")).pdf("0001202505290031")


def test_retries_then_success(monkeypatch):
    attempts = []

    class Resp:
        def __init__(self, body):
            self.body = body

        def read(self):
            return self.body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(req, timeout):
        attempts.append(req.get_header("User-agent"))
        if len(attempts) < 3:
            raise OSError("timeout")
        return Resp(json.dumps({"items": [], "itemsTotalCount": 0}).encode())

    monkeypatch.setattr(pravo.urllib.request, "urlopen", urlopen)
    t = pravo.HttpTransport(pause=0, sleep=lambda s: None)
    page = pravo.Client(t).search(Name="x")
    assert page.total == 0 and len(attempts) == 3
    assert attempts[0].startswith("openpalliative-watch")


def test_gives_up_after_retries(monkeypatch):
    monkeypatch.setattr(pravo.urllib.request, "urlopen", lambda req, timeout: (_ for _ in ()).throw(OSError("down")))
    t = pravo.HttpTransport(pause=0, sleep=lambda s: None)
    with pytest.raises(pravo.SourceUnavailable):
        pravo.Client(t).document_raw("0001202505290031")
