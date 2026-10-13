import { readFileSync } from "node:fs";
import { test, expect, checkA11y, noHorizontalScroll } from "../../opsite/tests/fixtures.js";
import { items, envelope, lib, isoToday, shiftIso, pickRule, fillDate, calc as fillCalc, hubSituations, printPages } from "./helpers.js";

const rules = items("deadline-rules");
const calendar = envelope("calendar");
const { computeDeadline } = await lib("deadlines.js");
const today = isoToday();
const forward = rules.filter((r) => r.direction === "forward" && r.from_event !== "turns-18");
const backward = rules.find((r) => r.direction === "backward");

function findStart(rule, pred, from = -3, to = -400) {
  for (let i = from; i >= to; i -= 1) {
    const start = shiftIso(today, i);
    const res = computeDeadline({ rule, start, calendar });
    if (pred(res)) return { start, res };
  }
  return null;
}

async function calc(page, rule, start) {
  await fillCalc(page, rule, start);
  await expect(page.locator(".pn-res__date")).toBeVisible();
}

test.describe("Посчитать срок", () => {

  test("правило и дата дают дату, формулу и шаги", async ({ page }) => {
    const rule = forward[0];
    const found = findStart(rule, (r) => r.latest >= today, -2, -10) || { start: shiftIso(today, -2), res: computeDeadline({ rule, start: shiftIso(today, -2), calendar }) };
    await page.goto("deadlines/");
    await calc(page, rule, found.start);
    await expect(page.locator(".pn-res__title")).toHaveText(rule.situation);
    await expect(page.locator(".pn-res__date")).toContainText(String(Number(found.res.due.slice(8))));
    await expect(page.locator(".pn-res__formula")).not.toBeEmpty();
    await expect(page.locator(".pn-res__steps li")).toHaveCount(found.res.steps.length);
    await expect(page.locator(".pn-res .pn-legal")).toContainText("Толкование не проверено юристом в РФ");
    await noHorizontalScroll(page);
    await checkA11y(page);
  });

  test("неоднозначное правило показывает две даты", async ({ page }) => {
    const rule = forward.find((r) => r.shift_if_nonworking === "unknown");
    test.skip(!rule, "нет правила с неизвестным переносом");
    const found = findStart(rule, (r) => Boolean(r.due_alt));
    test.skip(!found, "не нашлось даты с переносом");
    await page.goto("deadlines/");
    await calc(page, rule, found.start);
    await expect(page.locator('[data-part="alt"]')).toBeVisible();
    await expect(page.locator('[data-part="ambiguous"]')).toBeVisible();
  });

  test("прошедший срок даёт ссылку на жалобу с правилом и датой", async ({ page }) => {
    const rule = forward[0];
    const found = findStart(rule, (r) => r.latest < today, -40, -700);
    await page.goto("deadlines/");
    await calc(page, rule, found.start);
    const link = page.locator('[data-f="ok-link"]');
    await expect(link).toBeVisible();
    await expect(link).toHaveAttribute("href", `/obrashchenie-kit/case/#new=1&s=no-answer&rule=${rule.id}&from=${found.start}`);
    await expect(page.locator(".pn-res").getByRole("link", { name: "Куда обращаться дальше" })).toBeVisible();
  });

  test("фрагмент предзаполняет форму и исчезает из адреса", async ({ page }) => {
    const rule = forward[0];
    const start = shiftIso(today, -5);
    await hubSituations(page);
    await page.goto(`deadlines/#rule=${rule.id}&from=${start}&back=refused`);
    await expect(page.locator(".pn-res__date")).toBeVisible();
    await expect(page.locator(`input[name="rule"][value="${rule.id}"]`)).toBeChecked();
    expect(new URL(page.url()).hash).toBe("");
    await expect(page.locator(".pn-back")).toBeVisible();
    await expect(page.locator(".pn-back a")).toHaveAttribute("href", "/s/refused/");
  });

  test("обратный счёт до 18 лет не берёт дату из адреса", async ({ page }) => {
    test.skip(!backward, "нет правила обратного счёта");
    await page.goto(`deadlines/#rule=${backward.id}&from=${shiftIso(today, -1)}`);
    await expect(page.locator(`input[name="rule"][value="${backward.id}"]`)).toBeChecked();
    await expect(page.locator(".pn-result")).toBeHidden();
    await calc(page, backward, shiftIso(today, 500));
    const res = computeDeadline({ rule: backward, start: shiftIso(today, 500), calendar });
    if (res.margin_applied) await expect(page.locator('[data-part="unverified"]')).toContainText("запас");
  });

  test("ошибки формы", async ({ page }) => {
    await page.goto("deadlines/");
    await page.getByRole("button", { name: "Посчитать" }).click();
    await expect(page.locator("#pn-rule-error")).toBeVisible();
    await pickRule(page, forward[0].id);
    await expect(page.locator("#pn-rule-error")).toBeHidden();
    await page.getByRole("button", { name: "Посчитать" }).click();
    await expect(page.locator("#pn-date-error")).toContainText("Укажите дату");
    await page.locator("#pn-date-d").fill("31");
    await page.locator("#pn-date-m").selectOption("2");
    await page.locator("#pn-date-y").fill("2026");
    await page.getByRole("button", { name: "Посчитать" }).click();
    await expect(page.locator("#pn-date-error")).toContainText("Такой даты нет");
    await page.locator("#pn-date-y").fill("26");
    await page.getByRole("button", { name: "Посчитать" }).click();
    await expect(page.locator("#pn-date-error")).toContainText("Год четырьмя цифрами");
    await fillDate(page, shiftIso(today, 30));
    await page.getByRole("button", { name: "Посчитать" }).click();
    await expect(page.locator("#pn-date-error")).toContainText("не может быть позже сегодняшней");
    await checkA11y(page);
  });

  test("календарь .ics скачивается", async ({ page }) => {
    await page.goto("deadlines/");
    await calc(page, forward[0], shiftIso(today, -3));
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("button", { name: "Добавить в календарь" }).click(),
    ]);
    expect(download.suggestedFilename()).toMatch(/^srok-\d{4}-\d{2}-\d{2}\.ics$/);
    const text = readFileSync(await download.path(), "utf8");
    expect(text).toContain("BEGIN:VCALENDAR");
    expect(text).toContain("SUMMARY:Срок:");
    expect(text).toContain("TRIGGER:-P1D");
  });

  test("печать результата помещается на один лист", async ({ page, browserName }, info) => {
    const list = info.project.name === "desktop" ? rules : forward.slice(0, 1);
    for (const rule of list) {
      await page.goto("deadlines/");
      await calc(page, rule, rule.direction === "backward" ? shiftIso(today, 300) : shiftIso(today, -3));
      await page.evaluate(() => window.dispatchEvent(new Event("beforeprint")));
      expect(await printPages(page, browserName), rule.id).toBe(1);
    }
  });

  test("страница правила: #from= предзаполняет, считает и стирается", async ({ page }) => {
    const rule = forward[0];
    const start = shiftIso(today, -4);
    await page.goto(`deadlines/${rule.id}/#from=${start}`);
    await expect(page.locator(".pn-res__date")).toBeVisible();
    expect(new URL(page.url()).hash).toBe("");
    await expect(page.locator("#pn-date-y")).toHaveValue(start.slice(0, 4));
    await expect(page.locator("#pn-date-m")).toHaveValue(String(Number(start.slice(5, 7))));
    await expect(page.locator("#pn-date-d")).toHaveValue(String(Number(start.slice(8))));
    await expect(page.getByRole("link", { name: "Откуда этот срок" })).toBeHidden();
    await checkA11y(page);
  });

  test("кривой #from= не ломает страницу", async ({ page }) => {
    const rule = forward[0];
    await page.goto(`deadlines/${rule.id}/#from=2026-02-31`);
    await expect(page.locator(".pn-result")).toBeHidden();
    const other = forward[1] || forward[0];
    await page.goto(`deadlines/${other.id}/#from=<img src=x onerror=alert(1)>`);
    await expect(page.locator(".pn-calc__form")).toBeVisible();
    await expect(page.locator(".pn-result")).toBeHidden();
    await expect(page.locator("main img")).toHaveCount(0);
  });

  test("выбор варианта, «Сегодня» и результат с датой", async ({ page }) => {
    const rule = forward[0];
    await page.goto("deadlines/");
    await pickRule(page, rule.id);
    await expect(page.locator("#pn-date-d")).toBeFocused();
    await expect(page.locator("#pn-date")).toBeInViewport();
    await page.getByRole("button", { name: "Сегодня" }).click();
    await expect(page.locator("#pn-date-y")).toHaveValue(today.slice(0, 4));
    await page.getByRole("button", { name: "Посчитать" }).click();
    const res = computeDeadline({ rule, start: today, calendar });
    await expect(page.locator(".pn-res__date")).toContainText(String(Number(res.due.slice(8))));
    await expect(page.locator(".pn-res__title")).toBeFocused();
  });

  test("группы вариантов сворачиваются, выбранная раскрыта", async ({ page }) => {
    const other = rules.find((r) => r.group && r.group !== rules[0].group) || rules.at(-1);
    await page.goto("deadlines/");
    const groups = page.locator(".pn-calc__group");
    test.skip((await groups.count()) < 2, "одна группа");
    await expect(groups.first()).toHaveAttribute("open", "");
    await expect(groups.nth(1)).not.toHaveAttribute("open", "");
    await pickRule(page, other.id);
    const mine = page.locator(".pn-calc__group", { has: page.locator(`input[value="${other.id}"]`) });
    await expect(mine).toHaveAttribute("open", "");
    await expect(page.locator(".pn-calc__group[open]")).toHaveCount(1);
  });

  test("на телефоне «Все сроки» свёрнуты, страница короче 6000px", async ({ page }, info) => {
    test.skip(info.project.name !== "mobile");
    await page.goto("deadlines/");
    await expect(page.locator(".pn-all-rules__details")).not.toHaveAttribute("open", "");
    expect(await page.evaluate(() => document.documentElement.scrollHeight)).toBeLessThan(6000);
    await page.locator(".pn-all-rules__summary").click();
    await expect(page.locator(".pn-rule-table")).toBeVisible();
  });

  test("без JS таблица сроков раскрыта и полей даты нет @nojs", async ({ page }, info) => {
    test.skip(info.project.name !== "nojs");
    await page.goto("deadlines/");
    await expect(page.locator(".pn-rule-table")).toBeVisible();
    await expect(page.locator(".pn-calc__form")).toBeHidden();
    await expect(page.locator('input[type="date"]')).toHaveCount(0);
  });

  test("первый экран телефона: заголовок, черновик и два варианта @widths", async ({ page }, info) => {
    test.skip(info.project.name !== "w360");
    for (const size of [{ width: 360, height: 640 }, { width: 390, height: 844 }]) {
      await page.setViewportSize(size);
      await page.goto("deadlines/");
      await page.evaluate(() => document.fonts.ready);
      await expect(page.locator("h1")).toBeInViewport({ ratio: 1 });
      await expect(page.locator(".op-draft")).toBeInViewport({ ratio: 1 });
      const opts = page.locator(".pn-calc__opt");
      await expect(opts.nth(0)).toBeInViewport({ ratio: 1 });
      await expect(opts.nth(1)).toBeInViewport({ ratio: 1 });
    }
  });

  for (const id of ["100n-deferred", "100n-deferred-cito", "100n-deferred-purchase"]) {
    test(`сроки аптеки ${id}: строка про сильную боль`, async ({ page }) => {
      const rule = rules.find((r) => r.id === id);
      test.skip(!rule, "правила нет в данных");
      await page.goto(`deadlines/${id}/`);
      const warn = page.locator(".pn-rule > .pn-print-skip .pn-painnow");
      await expect(warn).toBeVisible();
      await expect(warn).toContainText("не ждите");
      await expect(warn.locator('a[href="tel:103"]')).toHaveCount(1);
      await expect(warn).toContainText("выездную паллиативную службу");
      await page.goto("deadlines/");
      await calc(page, rule, shiftIso(today, -1));
      await expect(page.locator(".pn-res .pn-painnow")).toBeVisible();
    });
  }

  test("не аптечное правило без строки про боль", async ({ page }) => {
    const rule = forward.find((r) => r.group !== "pharmacy");
    await page.goto("deadlines/");
    await calc(page, rule, shiftIso(today, -1));
    await expect(page.locator(".pn-res__date")).toBeVisible();
    await expect(page.locator(".pn-res .pn-painnow")).toBeHidden();
    await expect(page.locator("input[type=date]")).toHaveCount(0);
  });
  test("региональный нерабочий день: строка под результатом, дата не меняется", async ({ page }) => {
    const rule = forward.find((r) => r.unit === "working_days") || forward[0];
    const start = shiftIso(today, -1);
    const res = computeDeadline({ rule, start, calendar });
    const day = shiftIso(start, 1);
    const env = { ...calendar, regional: [{ region_id: "RU-TA", region_name: "Пример региона", region_in: "в регионе Пример", date: day, title: "Пример праздника", eoNumber: "0000000000000000", verified: false }] };
    await page.route("**/data/v1/calendar.json", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(env) }));
    await page.goto("deadlines/");
    await calc(page, rule, start);
    const box = page.locator(".pn-res__regional");
    await expect(box.locator("details summary")).toContainText("дополнительные нерабочие дни: 1");
    await expect(page.locator(".pn-res__date")).toContainText(String(Number(res.due.slice(8))));
    await page.evaluate(() => localStorage.setItem("op:region", "RU-TA"));
    await page.goto("about:blank");
    await page.goto("deadlines/");
    await calc(page, rule, start);
    await expect(box).toContainText("В регионе Пример в этот период был дополнительный нерабочий день");
    await expect(box).toContainText("толкование не проверено юристом в РФ");
    await expect(box.locator("details")).toHaveCount(0);
    await page.evaluate(() => localStorage.clear());
  });
});
