import { test } from "node:test";
import assert from "node:assert/strict";
import { regionalDays, regionalInRange } from "../../lib/regional.js";

const calendar = {
  items: [
    { id: "baseline", kind: "baseline" },
    { id: "2026", kind: "year", year: 2026 },
    { id: "demo-r1", kind: "regional", region_id: "RU-AAA", region_name: "Пример А", region_in: "в регионе Пример А", date: "2026-03-20", title: "Пример праздника", eoNumber: "0000000000000001", verified: true },
    { id: "demo-r2", kind: "regional", region_id: "RU-BBB", region_name: "Пример Б", days: [{ date: "2026-03-25", title: "Пример другого праздника" }, { date: "2026-06-01", title: "Пример летнего" }] },
  ],
};

test("день внутри интервала находится, дата начала не считается", () => {
  assert.deepEqual(regionalInRange(calendar, "2026-03-10", "2026-03-30").map((d) => d.date), ["2026-03-20", "2026-03-25"]);
  assert.deepEqual(regionalInRange(calendar, "2026-03-20", "2026-03-24"), []);
});

test("фильтр по региону пользователя", () => {
  const found = regionalInRange(calendar, "2026-03-01", "2026-12-31", "RU-BBB");
  assert.deepEqual(found.map((d) => d.date), ["2026-03-25", "2026-06-01"]);
  assert.equal(found[0].region_name, "Пример Б");
});

test("без регионального календаря и с плохими датами пусто", () => {
  assert.deepEqual(regionalInRange({ items: [{ kind: "year" }] }, "2026-01-01", "2026-12-31"), []);
  assert.deepEqual(regionalInRange(calendar, "2026-13-01", "x"), []);
  assert.equal(regionalDays(null).length, 0);
  assert.deepEqual(regionalInRange(calendar, "2026-04-01", "2026-03-01").map((d) => d.date), ["2026-03-20", "2026-03-25"]);
});

test("отдельный список calendar.regional и регион в нижнем регистре", () => {
  const cal = { items: [], regional: [{ region_id: "ru-ccc", region_name: "Пример В", date: "2026-05-15", title: "Пример", verified: false }] };
  const found = regionalInRange(cal, "2026-05-01", "2026-05-31", "RU-CCC");
  assert.equal(found.length, 1);
  assert.equal(found[0].region_id, "RU-CCC");
  assert.equal(found[0].verified, false);
});
