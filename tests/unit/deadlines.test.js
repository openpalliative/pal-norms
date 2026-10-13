import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { computeDeadline, isWorkingDay, addWorkingDays, nonWorkingDays, calendarYears, formulaOf } from "../../lib/deadlines.js";

const root = new URL("../../", import.meta.url);
const load = (p) => JSON.parse(readFileSync(new URL(p, root), "utf8"));
const calendar = load("_site/data/v1/calendar.json");
const rules = new Map(load("_site/data/v1/deadline-rules.json").items.map((r) => [r.id, r]));

function goldenCases() {
  const text = readFileSync(new URL("tests/golden/deadlines.yaml", root), "utf8");
  return text.split("\n").filter((l) => l.startsWith("- {")).map((l) => {
    const body = l.slice(3, -1);
    const out = {};
    for (const part of body.split(", ")) {
      const [k, v] = part.split(": ");
      out[k] = v === "null" ? null : v === "true" ? true : v === "false" ? false : /^\d+$/.test(v) ? Number(v) : v;
    }
    return out;
  });
}

test("эталон сроков: не меньше 30 случаев", () => {
  assert.ok(goldenCases().length >= 30);
});

for (const c of goldenCases()) {
  test(`${c.rule} от ${c.start}`, () => {
    const rule = rules.get(c.rule);
    assert.ok(rule, `нет правила ${c.rule}`);
    const r = computeDeadline({ rule, start: c.start, calendar });
    assert.equal(r.due, c.due);
    if ("due_alt" in c) assert.equal(r.due_alt, c.due_alt);
    if ("margin" in c) assert.equal(r.margin_applied, c.margin);
    if ("calendar_verified" in c) assert.equal(r.calendar_verified, c.calendar_verified);
    if ("extended" in c) assert.equal(r.extended, c.extended);
    assert.equal(r.rule_id, c.rule);
    assert.ok(r.formula.length > 0);
    assert.equal(r.steps[0].date, c.start);
  });
}

test("рабочая суббота и перенесённый выходной", () => {
  assert.deepEqual(isWorkingDay("2027-02-20", calendar), { working: true, verified: true });
  assert.deepEqual(isWorkingDay("2027-02-22", calendar), { working: false, verified: true });
  assert.deepEqual(isWorkingDay("2025-11-01", calendar), { working: true, verified: true });
  assert.equal(isWorkingDay("2028-01-03", calendar).verified, false);
  assert.equal(isWorkingDay("2028-01-03", calendar).working, false);
});

test("перенос праздника с выходного по ч. 2 ст. 112 вне утверждённых лет", () => {
  assert.equal(isWorkingDay("2028-11-04", calendar).working, false);
  assert.equal(isWorkingDay("2028-11-06", calendar).working, false);
  assert.equal(isWorkingDay("2028-11-07", calendar).working, true);
  assert.equal(isWorkingDay("2029-11-05", calendar).working, false);
  assert.equal(isWorkingDay("2028-01-10", calendar).working, true);
});

test("сложение рабочих дней в обе стороны", () => {
  assert.equal(addWorkingDays("2026-12-30", 1, calendar), "2027-01-11");
  assert.equal(addWorkingDays("2027-01-11", -1, calendar), "2026-12-30");
  assert.equal(addWorkingDays("2026-03-06", 0, calendar), "2026-03-06");
});

test("список нерабочих дней", () => {
  const days = nonWorkingDays("2027-02-19", "2027-02-24", calendar);
  assert.deepEqual(days, [
    { date: "2027-02-21", kind: "weekend" },
    { date: "2027-02-22", kind: "transfer" },
    { date: "2027-02-23", kind: "holiday" },
  ]);
});

test("годы календаря", () => {
  const y = calendarYears(calendar);
  for (const year of [2025, 2026, 2027]) assert.equal(y[year].verified, true);
});

test("формула по-русски без номеров актов", () => {
  assert.match(formulaOf(rules.get("59fz-answer")), /^30 календарных дней, 3 календарных дня на регистрацию/);
  assert.match(formulaOf(rules.get("208n-p23-transition")), /90 рабочих дней до события/);
  assert.equal(formulaOf(rules.get("789n-inpatient")), "в течение суток");
  for (const r of rules.values()) assert.doesNotMatch(formulaOf(r), /\d+[нН]\b|ФЗ|—|–/);
});

test("неверная дата даёт понятную ошибку", () => {
  assert.throws(() => computeDeadline({ rule: rules.get("100n-deferred"), start: "2026-02-30", calendar }), /Такой даты нет/);
  assert.throws(() => computeDeadline({ rule: rules.get("100n-deferred"), start: "30.02.2026", calendar }), /ГГГГ-ММ-ДД/);
});
