import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { isWorkingDay, addDays } from "../../lib/deadlines.js";

const root = new URL("../../", import.meta.url);
const calendar = JSON.parse(readFileSync(new URL("_site/data/v1/calendar.json", root), "utf8"));

function golden() {
  const out = {};
  let year = null;
  for (const line of readFileSync(new URL("tests/golden/calendar.yaml", root), "utf8").split("\n")) {
    const y = /^ {2}(\d{4}):$/.exec(line);
    if (y) {
      year = Number(y[1]);
      out[year] = {};
      continue;
    }
    const kv = /^ {4}(\w+): (.*)$/.exec(line);
    if (!kv || year === null) continue;
    const [, key, value] = kv;
    out[year][key] = value.startsWith("[") ? value.slice(1, -1).split(",").map((s) => s.trim()).filter(Boolean) : Number(value);
  }
  return out;
}

for (const [year, g] of Object.entries(golden())) {
  test(`календарь ${year} совпадает с эталоном по каждому дню`, () => {
    const off = new Set(g.off_weekdays);
    const work = new Set(g.work_weekends);
    let working = 0;
    for (let d = `${year}-01-01`; d.startsWith(year); d = addDays(d, 1)) {
      const wd = new Date(`${d}T00:00:00Z`).getUTCDay();
      const weekend = wd === 0 || wd === 6;
      const expected = weekend ? work.has(d) : !off.has(d);
      const got = isWorkingDay(d, calendar);
      assert.equal(got.working, expected, d);
      assert.equal(got.verified, true, d);
      if (expected) working += 1;
    }
    assert.equal(working, g.working_days);
  });
}
