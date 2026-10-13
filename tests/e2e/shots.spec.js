import { mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { test, expect, setSize } from "../../opsite/tests/fixtures.js";
import { items, isoToday, shiftIso, calc, pickRule, lib, envelope, printPages } from "./helpers.js";

test.use({ bypassCSP: process.env.OP_BROWSER === "webkit" });

const pages = JSON.parse(readFileSync(join(process.cwd(), "tests/e2e/pages.json"), "utf8"));
const dir = join(process.cwd(), "_reports", "shots", "pal-norms");
const rules = items("deadline-rules");
const calendar = envelope("calendar");
const { computeDeadline } = await lib("deadlines.js");
const today = isoToday();
const forward = rules.filter((r) => r.direction === "forward" && r.from_event !== "turns-18");
const golden = (() => {
  try {
    return readFileSync(join(process.cwd(), "tests/golden/lint/memo.txt"), "utf8");
  } catch {
    return "Справку выдаёт ПФР по приказу 345н/372н";
  }
})();

async function snap(page, name, info, { themes = ["light", "dark"] } = {}) {
  mkdirSync(dir, { recursive: true });
  const browser = process.env.OP_BROWSER || "chromium";
  const tag = `${info.project.name}${browser === "chromium" ? "" : `-${browser}`}`;
  await page.evaluate(() => document.fonts.ready);
  for (const theme of themes) {
    await page.emulateMedia({ colorScheme: theme, media: "screen" });
    await page.waitForTimeout(60);
    await page.screenshot({ path: join(dir, `${tag}-${theme}-${name}.png`), fullPage: true, caret: "initial" });
  }
}

const STATES = {
  "deadlines-result": async (page) => {
    const rule = forward.find((r) => r.ambiguous) || forward[0];
    await page.goto("deadlines/");
    await calc(page, rule, shiftIso(today, -3));
    await expect(page.locator(".pn-res__date")).toBeVisible();
  },
  "deadlines-overdue": async (page) => {
    const rule = forward[0];
    let start = shiftIso(today, -90);
    for (let i = 40; i < 400; i += 1) {
      const s = shiftIso(today, -i);
      if (computeDeadline({ rule, start: s, calendar }).latest < today) { start = s; break; }
    }
    await page.goto("deadlines/");
    await calc(page, rule, start);
    await expect(page.locator('[data-part="passed"]')).toBeVisible();
  },
  "deadlines-pharmacy": async (page) => {
    const rule = rules.find((r) => r.group === "pharmacy") || forward[0];
    await page.goto("deadlines/");
    await calc(page, rule, shiftIso(today, -1));
    await expect(page.locator(".pn-res__date")).toBeVisible();
  },
  "deadlines-errors": async (page) => {
    await page.goto("deadlines/");
    await page.getByRole("button", { name: "Посчитать" }).click();
    await pickRule(page, forward[0].id);
    await page.locator("#pn-date-d").fill("31");
    await page.locator("#pn-date-m").selectOption("2");
    await page.locator("#pn-date-y").fill("2026");
    await page.getByRole("button", { name: "Посчитать" }).click();
    await expect(page.locator("#pn-date-error")).toBeVisible();
  },
  "check-findings": async (page) => {
    await page.goto("check/");
    await page.getByLabel("Текст памятки, шаблона или письма").fill(golden);
    await page.getByRole("button", { name: "Проверить" }).click();
    await expect(page.locator(".pn-check__result")).toBeVisible();
  },
  "indications-group": async (page) => {
    await page.goto("indications/");
    const select = page.getByLabel("Показать одну группу");
    await select.selectOption({ index: 4 });
  },
  "404": async (page) => {
    await page.goto("no-such-page/");
  },
};

for (const p of pages) {
  test(`снимок ${p.name} @shots @widths`, async ({ page }, info) => {
    test.skip(info.project.name === "nojs");
    await page.goto(p.path);
    await snap(page, p.name, info);
  });
}

for (const [name, run] of Object.entries(STATES)) {
  test(`снимок состояния ${name} @shots @widths`, async ({ page }, info) => {
    test.skip(info.project.name === "nojs");
    await run(page);
    await snap(page, name, info);
  });
}

test("снимки при A++ на 360 @shots @widths", async ({ page }, info) => {
  test.skip(info.project.name !== "w360");
  await setSize(page, "xl");
  for (const p of pages) {
    await page.goto(p.path);
    await expect(page.locator("html")).toHaveAttribute("data-size", "xl");
    await snap(page, `xl-${p.name}`, info, { themes: ["light"] });
  }
  await STATES["deadlines-result"](page);
  await snap(page, "xl-deadlines-result", info, { themes: ["light", "dark"] });
});

test("печать результата и календаря 2027 по одному листу @shots", async ({ page, browserName }, info) => {
  test.skip(info.project.name !== "desktop");
  await STATES["deadlines-result"](page);
  await page.evaluate(() => window.dispatchEvent(new Event("beforeprint")));
  expect(await printPages(page, browserName)).toBe(1);
  await page.evaluate(() => window.dispatchEvent(new Event("beforeprint")));
  await expect(page.locator(".pn-res__quotes")).toHaveAttribute("open", "");
  await page.emulateMedia({ media: "print", colorScheme: "light" });
  await page.screenshot({ path: join(dir, `${info.project.name}-${browserName}-print-deadlines-result.png`), fullPage: true, caret: "initial" });
  await page.emulateMedia({ media: null });
  await page.goto("calendar/2027/");
  expect(await printPages(page, browserName)).toBe(1);
  await page.emulateMedia({ media: "print", colorScheme: "light" });
  await page.screenshot({ path: join(dir, `${info.project.name}-${browserName}-print-calendar-2027.png`), fullPage: true, caret: "initial" });
});
