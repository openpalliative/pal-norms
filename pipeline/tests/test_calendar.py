import datetime as dt

import holidays

from pipeline import calendar
from pipeline.tests.conftest import ROOT


def years():
    return {int(i["id"]): i for i in calendar.items(ROOT) if i["kind"] == "year"}


def weekday_off(off):
    return {d for d in off if dt.date.fromisoformat(d).weekday() < 5}


def test_2025_matches_holidays_package():
    ref = {d.isoformat() for d in holidays.country_holidays("RU", years=2025)}
    assert weekday_off(years()[2025]["off"]) == weekday_off(ref)


def test_baseline_holidays_match_package():
    ref = holidays.country_holidays("RU", years=2027)
    fixed = {d.strftime("%m-%d") for d, name in ref.items() if "перенес" not in name.lower()}
    base = calendar.load(ROOT)[0]
    assert set(base["holidays_mmdd"]) == fixed


def test_package_days_are_subset_for_2026_and_2027():
    for y in (2026, 2027):
        ref = {d.isoformat() for d in holidays.country_holidays("RU", years=y)}
        assert ref <= set(years()[y]["off"])


def test_known_2026_and_2027_days():
    y = years()
    assert {"2026-01-09", "2026-03-09", "2026-05-11", "2026-12-31"} <= set(y[2026]["off"])
    assert {"2027-02-22", "2027-05-03", "2027-05-10", "2027-06-14", "2027-11-05", "2027-12-31"} <= set(y[2027]["off"])
    assert y[2027]["work"] == ["2027-02-20"]
    assert y[2025]["work"] == ["2025-11-01"]


def test_carry_over_skips_holiday_moved_by_decree():
    base = {"holidays_mmdd": ["02-23", "03-08"], "carry_over": "true", "carry_exclude_mmdd": []}
    off, work = calendar.year_days(2025, base, [{"from": "2025-02-23", "to": "2025-05-08"}])
    assert "2025-02-24" not in off and "2025-03-10" in off and "2025-05-08" in off
    assert work == []


def test_2024_matches_holidays_package():
    ref = {d.isoformat() for d in holidays.country_holidays("RU", years=2024)}
    assert weekday_off(years()[2024]["off"]) == weekday_off(ref)
    assert years()[2024]["work"] == ["2024-04-27", "2024-11-02", "2024-12-28"]


def test_golden_calendar_by_day():
    import yaml
    gold = yaml.safe_load((ROOT / "tests" / "golden" / "calendar.yaml").read_text(encoding="utf-8"))["years"]
    y = years()
    for year, g in gold.items():
        off = {d.isoformat() for d in g["off_weekdays"]}
        work = {d.isoformat() for d in g["work_weekends"]}
        assert weekday_off(y[year]["off"]) == off, year
        assert set(y[year]["work"]) == work, year
        days = [dt.date(year, 1, 1) + dt.timedelta(n) for n in range(366)]
        working = sum(1 for d in days if d.year == year and (d.isoformat() in work or (d.weekday() < 5 and d.isoformat() not in off)))
        assert working == g["working_days"], year
