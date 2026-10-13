import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { checkText, normalize } from "../../lib/textcheck.js";

const root = new URL("../../", import.meta.url);
const load = (p) => JSON.parse(readFileSync(new URL(p, root), "utf8"));
const rules = load("_site/data/v1/lint-rules.json");
const acts = load("_site/data/v1/acts.json");
const dir = new URL("tests/golden/lint/", root);

for (const name of readdirSync(dir).filter((f) => f.endsWith(".txt"))) {
  test(`эталон ${name} совпадает с Python`, () => {
    const text = readFileSync(new URL(name, dir), "utf8");
    const expected = JSON.parse(readFileSync(new URL(name.replace(/\.txt$/, ".expected.json"), dir), "utf8"));
    assert.deepEqual(checkText(text, rules, { acts }), expected);
  });
}

test("памятка ловит все правила", () => {
  const text = readFileSync(new URL("memo.txt", dir), "utf8");
  const ids = new Set(checkText(text, rules, { acts }).map((f) => f.rule_id));
  for (const r of rules.items) assert.ok(ids.has(r.id), `правило ${r.id} не сработало`);
});

test("действующие документы не трогаем", () => {
  const text = "Положение 208н/243н, перечень 398н, врачебная комиссия по приказу 180н, СФР, Фонд пенсионного и социального страхования";
  assert.deepEqual(checkText(text, rules), []);
});

test("30 рабочих дней без 18 лет не срабатывает", () => {
  assert.deepEqual(checkText("Срок ответа 30 рабочих дней.", rules), []);
  assert.equal(checkText("За 30 рабочих дней до 18 лет", rules).length, 1);
});

test("номер без контекста паллиативной помощи не срабатывает", () => {
  assert.deepEqual(checkText("Приказ 345н о перевозках", rules), []);
  assert.equal(checkText("Паллиативная помощь по приказу 345н", rules)[0].rule_id, "lint-345n-372n");
});

test("нормализация пробелов и знака номера", () => {
  assert.equal(normalize("№187н и\tтекст"), "№ 187н и текст");
  const f = checkText("паллиативная помощь: приказ № 187-н", rules);
  assert.equal(f.length, 1);
  assert.equal(f[0].fragment, "187-н");
});

test("строка и столбец находки", () => {
  const f = checkText("первая строка\nпаллиативная помощь, приказ 193н", rules);
  assert.equal(f[0].line, 2);
  assert.equal(f[0].col, 29);
});

test("пустой текст", () => {
  assert.deepEqual(checkText("", rules), []);
  assert.deepEqual(checkText(undefined, rules), []);
});
