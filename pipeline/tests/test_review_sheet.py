import pytest

from opsite.data import BuildError
from pipeline import check, export, review_ingest, review_sheet
from pipeline.io import read_yaml


@pytest.mark.parametrize("target,kind", [("505n-p4", "quote"), ("505n-vk-decision", "rule"), ("adults-p4-1", "indication"),
                                         ("1195n", "act"), ("esc-no-answer", "escalation")])
def test_sheet_has_quote_crop_and_questions(tmp_root, target, kind):
    page, template = review_sheet.render(tmp_root, target)
    assert "Нужна проверка юристом (или медиком) в РФ" in page
    assert page.count('<span class="box"></span>') == 3 * len(review_sheet.QUESTIONS[kind])
    for word in ("Верно", "Неверно", "Не знаю"):
        assert f"<th>{word}</th>" in page
    if kind in ("quote", "rule", "indication", "act"):
        assert "data:image/png;base64," in page
        assert "0001201909250013" in page or "0001202505290031" in page or "0001202508130021" in page
    assert f"target: {target}" in template


def test_sheet_unknown_target(tmp_root):
    with pytest.raises(LookupError):
        review_sheet.render(tmp_root, "nope")


def test_ingest_template_roundtrip(tmp_root, tmp_path):
    _, template = review_sheet.render(tmp_root, "505n-vk-decision")
    src = tmp_path / "answer.yaml"
    src.write_text(template.replace("reviewed_at: ", "reviewed_at: 2026-10-01  # ").replace("ref:", "ref: https://example.org/1"),
                   encoding="utf-8")
    out = review_ingest.ingest(tmp_root, src)
    assert out == tmp_root / "data" / "review" / "505n-vk-decision.yaml"
    r = read_yaml(out)["reviews"][0]
    assert r["expires_at"] == "2027-10-01" and r["verdict"] == "ok"
    assert {q["id"] for q in r["questions"]} == {"value", "start", "shift", "who"}
    envs = {e["dataset"]: e for e in export.datasets(tmp_root)}
    assert check.check_reviews(tmp_root, envs) == []
    rule = {x["id"]: x for x in envs["deadline-rules"]["items"]}["505n-vk-decision"]
    assert rule["legal_review"]["reviewed_at"] == "2026-10-01"
    review_ingest.ingest(tmp_root, src)
    assert len(read_yaml(out)["reviews"]) == 1


def test_ingest_rejects_bad_file(tmp_root, tmp_path):
    src = tmp_path / "bad.yaml"
    src.write_text("target_kind: rule\ntarget: nope\nrole: lawyer\nreviewed_at: 2026-10-01\nexpires_after: 1y\nverdict: ok\n",
                   encoding="utf-8")
    with pytest.raises(BuildError):
        review_ingest.ingest(tmp_root, src)
    src.write_text("target_kind: rule\ntarget: 505n-p4\nrole: judge\nreviewed_at: 01.10.2026\nexpires_after: year\nverdict: maybe\n",
                   encoding="utf-8")
    with pytest.raises(BuildError):
        review_ingest.ingest(tmp_root, src)
