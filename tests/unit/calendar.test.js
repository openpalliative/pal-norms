import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { isWorkingDay, addDays } from "../../lib/deadlines.js";

const root = new URL("../../", import.meta.url);
const calendar = JSON.parse(readFileSync(new URL("_site/data/v1/calendar.json", root), "utf8"));
const byYear = new Map(calendar.items.filter((i) => i.kind === "year").map((i) => [i.year, i]));

function workingDays(year) {
  let n = 0;
  for (let d = `${year}-01-01`; d.startsWith(String(year)); d = addDays(d, 1)) if (isWorkingDay(d, calendar).working) n += 1;
  return n;
}

test("годы 2025-2027 проверены и опираются на постановления", () => {
  for (const year of [2025, 2026, 2027]) {
    const y = byYear.get(year);
    assert.equal(y.verified, true);
    assert.match(y.decree_eoNumber, /^\d{16}$/);
    assert.ok(y.quote_ids.length > 0);
  }
});

test("число рабочих дней в году совпадает с опубликованными календарями 2025 и 2026", () => {
  assert.equal(workingDays(2025), 247);
  assert.equal(workingDays(2026), 247);
});

test("перенесённые дни попадают в нерабочие", () => {
  for (const y of byYear.values()) {
    for (const t of y.transfers) assert.ok(y.off.includes(t.to), `${t.to} нет среди нерабочих`);
  }
});

test("праздники ст. 112 есть в каждом году", () => {
  const base = calendar.items.find((i) => i.kind === "baseline");
  for (const y of byYear.values()) {
    for (const md of base.holidays_mmdd) assert.ok(y.off.includes(`${y.year}-${md}`));
  }
});
