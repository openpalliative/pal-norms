import datetime as dt
import json
import shutil

from pipeline import watch
from pipeline.io import dump_yaml, read_yaml
from pipeline.pravo import Client
from pipeline.tests.conftest import ROOT

FIX = ROOT / "pipeline" / "tests" / "fixtures" / "pravo"
NOW = dt.datetime(2026, 10, 11, 14, 32, 29, tzinfo=dt.timezone.utc)


def fresh(tmp_root):
    (tmp_root / watch.STATE_PATH).unlink(missing_ok=True)
    return tmp_root


def client(folder=FIX, fail=False):
    return Client(watch.FixtureTransport(folder, fail=fail))


def kinds(report):
    return [r["kind"] for r in report["review"]]


def test_replay_is_quiet_and_fills_state(tmp_root):
    report, state, decrees = watch.run(client(), fresh(tmp_root), NOW)
    assert report["ok"] is True and report["review"] == [] and decrees == []
    assert state["last_ok_at"] == "2026-10-11T14:32:29Z"
    assert "0001202505290031" in state["seen"]
    assert state["queries"]["transfers"]["last_eo"] == "0001202609180037"
    assert set(report) >= {"checked_at", "facts", "review"}


def test_amendment_is_found(tmp_root):
    def drop(d):
        next(a for a in d["acts"] if a["id"] == "187n")["amended_by"] = []
    path = tmp_root / "data" / "acts.yaml"
    data = read_yaml(path)
    drop(data)
    dump_yaml(data, path)
    report, _, _ = watch.run(client(), fresh(tmp_root), NOW)
    assert kinds(report) == ["amendment_or_repeal"]
    assert report["review"][0]["eoNumber"] == "0001201808200006"


def test_transfer_decree_draft(tmp_root):
    path = tmp_root / "data" / "calendar" / "transfers.yaml"
    data = read_yaml(path)
    expected = next(y for y in data["years"] if y["year"] == "2027")["transfers"]
    data["years"] = [y for y in data["years"] if y["year"] != "2027"]
    dump_yaml(data, path)
    acts_path = tmp_root / "data" / "acts.yaml"
    acts = read_yaml(acts_path)
    acts["acts"] = [a for a in acts["acts"] if a["id"] != "pp-1187"]
    dump_yaml(acts, acts_path)
    report, _, decrees = watch.run(client(), fresh(tmp_root), NOW)
    assert "transfer_decree" in kinds(report)
    assert decrees[0]["eoNumber"] == "0001202609180037" and decrees[0]["year"] == 2027
    text = next(q for q in read_yaml(tmp_root / "data" / "quotes" / "pp-1187.yaml")["quotes"])["text"]
    files = watch.draft_decree(None, tmp_root, decrees[0], "2026-10-11", ocr_text=text)
    assert files == ["data/calendar/transfers.yaml", "data/changes.yaml"]
    year = next(y for y in read_yaml(path)["years"] if y["year"] == "2027")
    assert year["verified"] == "false" and year["transfers"] == expected
    assert read_yaml(tmp_root / "data" / "changes.yaml")["changes"][0]["kind"] == "transfer_decree"
    assert watch.draft_decree(None, tmp_root, decrees[0], "2026-10-11", ocr_text=text) == []


def test_new_act_from_topic_search(tmp_root, tmp_path):
    folder = tmp_path / "fix"
    shutil.copytree(FIX, folder)
    index = json.loads((folder / "index.json").read_text(encoding="utf-8"))
    key = watch.request_key("/api/Documents", {"PageSize": 30, "Index": 1, "Name": "паллиативной",
                                               "Block": "federal_authorities"})
    page = json.loads((folder / index[key]).read_text(encoding="utf-8"))
    page["items"].insert(0, {"eoNumber": "0001202610050001", "publishDateShort": "2026-10-05T00:00:00",
                             "complexName": "Приказ Министерства здравоохранения Российской Федерации от 01.10.2026 № 1н "
                                            "\"Пример нового порядка оказания паллиативной медицинской помощи\"",
                             "pagesCount": 3, "pdfFileLength": 1000, "name": "Пример"})
    (folder / index[key]).write_text(json.dumps(page, ensure_ascii=False), encoding="utf-8")
    report, state, _ = watch.run(client(folder), fresh(tmp_root), NOW)
    assert kinds(report) == ["new_act"]
    assert "0001202610050001" in state["seen"]


def test_republished_document(tmp_root):
    _, state, _ = watch.run(client(), fresh(tmp_root), NOW)
    state["seen"]["0001202505290031"]["pdfFileLength"] = 1
    watch.write_state(tmp_root, state)
    report, _, _ = watch.run(client(), tmp_root, NOW)
    assert kinds(report) == ["republished"]


def test_source_format_changes_nothing(tmp_root, tmp_path):
    folder = tmp_path / "fix"
    shutil.copytree(FIX, folder)
    index = json.loads((folder / "index.json").read_text(encoding="utf-8"))
    key = watch.request_key("/api/Document", {"eoNumber": watch.CANARY_EO})
    doc = json.loads((folder / index[key]).read_text(encoding="utf-8"))
    del doc["pagesCount"]
    (folder / index[key]).write_text(json.dumps(doc), encoding="utf-8")
    before = watch.load_state(fresh(tmp_root))
    report, state, _ = watch.run(client(folder), tmp_root, NOW)
    assert kinds(report) == ["source_format"] and report["ok"] is False
    assert state["seen"] == before["seen"] and state["last_ok_at"] == before["last_ok_at"]


def test_network_failure_keeps_state(tmp_root):
    _, ok_state, _ = watch.run(client(), fresh(tmp_root), NOW)
    watch.write_state(tmp_root, ok_state)
    for n in (1, 2, 3):
        report, state, _ = watch.run(client(fail=True), tmp_root, NOW + dt.timedelta(days=7 * n))
        watch.write_state(tmp_root, state)
        assert state["consecutive_failures"] == n
        assert state["last_ok_at"] == ok_state["last_ok_at"] and state["seen"] == ok_state["seen"]
    assert kinds(report) == ["unreachable"]
    _, state, _ = watch.run(client(), tmp_root, NOW + dt.timedelta(days=28))
    assert state["consecutive_failures"] == 0


def test_sunset_soon(tmp_root):
    path = tmp_root / "data" / "acts.yaml"
    data = read_yaml(path)
    next(a for a in data["acts"] if a["id"] == "1094n")["valid_until"] = "2026-12-01"
    dump_yaml(data, path)
    report, _, _ = watch.run(client(), fresh(tmp_root), NOW)
    assert kinds(report) == ["sunset_soon"]


def test_issues_are_not_duplicated():
    report = {"checked_at": "2026-10-11T00:00:00Z", "review": [
        watch.review("new_act", "Новый документ", "текст", "0001202610050001"),
        watch.review("sunset_soon", "Скоро истекает", "текст", "0001202111300115"),
        watch.review("transfer_decree", "Перенос", "текст", "0001202609180037"),
    ]}
    existing = watch.issue_title(report["review"][0])
    calls = []

    class Res:
        def __init__(self, out):
            self.stdout = out

    def runner(cmd, **kw):
        calls.append(cmd)
        if cmd[:3] == ["gh", "issue", "list"]:
            return Res(json.dumps([{"title": existing}]) if report["review"][0]["key"] in cmd[6] else "[]")
        return Res("")

    created = watch.open_issues(report, runner)
    assert created == [watch.issue_title(report["review"][1])]
    assert sum(1 for c in calls if c[:3] == ["gh", "issue", "create"]) == 1


def test_issue_key_is_stable():
    a = watch.review("new_act", "x", "y", "0001202610050001")
    b = watch.review("new_act", "другой заголовок", "z", "0001202610050001")
    assert a["key"] == b["key"] and len(a["key"]) == 8


def test_parse_transfers_matches_calendar():
    years = {y["year"]: y for y in read_yaml(ROOT / "data" / "calendar" / "transfers.yaml")["years"]}
    for act, year in (("pp-1335", "2025"), ("pp-1466", "2026"), ("pp-1187", "2027")):
        text = read_yaml(ROOT / "data" / "quotes" / f"{act}.yaml")["quotes"][0]["text"]
        assert watch.parse_transfers(text, int(year)) == years[year]["transfers"]


def test_mentions_date_both_forms():
    assert watch.mentions_date("утвержденный приказом от 14 апреля 2015 г. № 187н", "2015-04-14")
    assert watch.mentions_date("от 14.04.2015 № 187н", "2015-04-14")
    assert not watch.mentions_date("от 15.04.2015 № 187н", "2015-04-14")


def _edit_response(folder, params, change):
    index = json.loads((folder / "index.json").read_text(encoding="utf-8"))
    key = watch.request_key("/api/Documents", params)
    page = json.loads((folder / index[key]).read_text(encoding="utf-8"))
    change(page)
    (folder / index[key]).write_text(json.dumps(page, ensure_ascii=False), encoding="utf-8")


def _noeo_params(act_id):
    a = next(x for x in read_yaml(ROOT / "data" / "acts.yaml")["acts"] if x["id"] == act_id)
    return {"PageSize": 30, "Index": 1, "Name": watch.title_query(a["title"]), "Block": watch.BLOCKS[a["kind"]]}


def _item(eo, title, date="2026-10-05T00:00:00"):
    return {"eoNumber": eo, "publishDateShort": date, "complexName": title, "pagesCount": 2, "pdfFileLength": 900,
            "name": title}


def test_acts_without_eo_first_run_is_baseline(tmp_root):
    report, state, _ = watch.run(client(), fresh(tmp_root), NOW)
    assert report["review"] == []
    assert {b["act_id"] for b in report["baseline"]} >= {"tk-rf", "2347-r"}
    assert state["queries"]["noeo:59-fz"]["total"] >= 6


def test_new_amendment_to_59fz_without_eo(tmp_root, tmp_path):
    _, state, _ = watch.run(client(), fresh(tmp_root), NOW)
    watch.write_state(tmp_root, state)
    folder = tmp_path / "fix"
    shutil.copytree(FIX, folder)
    title = ("Федеральный закон от 01.10.2026 № 999-ФЗ \"О внесении изменений в Федеральный закон \"О порядке "
             "рассмотрения обращений граждан Российской Федерации\"")
    _edit_response(folder, _noeo_params("59-fz"), lambda p: p["items"].insert(0, _item("0001202610050002", title)))
    report, _, _ = watch.run(client(folder), tmp_root, NOW)
    assert kinds(report) == ["amendment_or_repeal"]
    assert report["review"][0]["eoNumber"] == "0001202610050002"
    assert "59-ФЗ" in report["review"][0]["body"]


def test_known_amendments_of_59fz_give_no_issue(tmp_root):
    _, state, _ = watch.run(client(), fresh(tmp_root), NOW)
    state["seen"] = {}
    watch.write_state(tmp_root, state)
    report, _, _ = watch.run(client(), tmp_root, NOW)
    assert not [r for r in report["review"] if "обращений" in r["title"] + r["body"]]
    amended = {m["eoNumber"] for a in read_yaml(tmp_root / "data" / "acts.yaml")["acts"] if a["id"] == "59-fz"
               for m in a["amended_by"]}
    assert {"0001202412280052", "0001201511040009", "0001201307030016", "0001201305080015"} <= amended


def test_excluded_territory_title_gives_no_issue(tmp_root, tmp_path):
    folder = tmp_path / "fix"
    shutil.copytree(FIX, folder)
    region = "Донецкой " + "Народной Республики"
    title = f"Приказ Министерства здравоохранения {region} от 01.10.2026 № 5 \"Об организации паллиативной помощи\""
    _edit_response(folder, {"PageSize": 30, "Index": 1, "Name": "паллиативной", "Block": "federal_authorities"},
                   lambda p: p["items"].insert(0, _item("0001202610050003", title)))
    report, state, _ = watch.run(client(folder), fresh(tmp_root), NOW)
    assert report["review"] == []
    assert report["skipped_territory"] == 1
    assert "0001202610050003" in state["seen"]


def test_external_title_is_neutralised(tmp_root, tmp_path):
    folder = tmp_path / "fix"
    shutil.copytree(FIX, folder)
    title = "@octocat [x](https://e.example) о паллиативной помощи " + "а" * 400
    _edit_response(folder, {"PageSize": 30, "Index": 1, "Name": "паллиативной", "Block": "federal_authorities"},
                   lambda p: p["items"].insert(0, _item("0001202610050004", title)))
    report, _, _ = watch.run(client(folder), fresh(tmp_root), NOW)
    assert kinds(report) == ["new_act"]
    item = report["review"][0]
    for text in (item["title"], item["body"]):
        assert "@octocat" not in text and "](" not in text and "https://" not in text
    assert "@ octocat" in item["body"] and "\\[x\\]\\(https[:]//e.example\\)" in item["body"]
    assert len(watch.clean_external(title)) <= watch.EXTERNAL_LIMIT
