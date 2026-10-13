import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const root = new URL("../../", import.meta.url);
const rules = JSON.parse(readFileSync(new URL("_site/data/v1/deadline-rules.json", root), "utf8")).items;
const golden = readFileSync(new URL("tests/golden/deadlines.yaml", root), "utf8")
  .split("\n").map((l) => /rule: ([^,]+),/.exec(l)).filter(Boolean).map((m) => m[1]);

for (const r of rules) {
  test(`у правила ${r.id} не меньше двух эталонных случаев`, () => {
    assert.ok(golden.filter((g) => g === r.id).length >= 2, r.id);
  });
}

test("в эталоне есть рабочие субботы 2027 и переход через новогодние праздники", () => {
  const text = readFileSync(new URL("tests/golden/deadlines.yaml", root), "utf8");
  assert.match(text, /start: 2027-02-1\d/);
  assert.match(text, /start: 2026-12-(29|30)/);
  assert.match(text, /start: 2024-12-/);
});
