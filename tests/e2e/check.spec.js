import { test, expect, checkA11y } from "../../opsite/tests/fixtures.js";
import { items, goldenLint } from "./helpers.js";

const rules = items("lint-rules");
const golden = goldenLint();
const demo = rules.some((r) => r.id.startsWith("demo-"));
const sample = golden || (demo ? {
  text: "Памятка для семьи.\nПо приказу 111н/111н помощь оказывают на дому.\nСправку выдаёт ПФР.\nЗа 30 рабочих дней до 18 лет сведения передают во взрослую сеть.",
  count: 3,
} : null);

test.describe("Проверить памятку", () => {
  test("находит все правила и ничего не хранит", async ({ page }) => {
    test.skip(!sample, "нет эталонной памятки");
    await page.goto("check/");
    await page.getByLabel("Текст памятки, шаблона или письма").fill(sample.text);
    await page.getByRole("button", { name: "Проверить" }).click();
    await expect(page.locator(".pn-check__count")).toHaveText(`Найдено: ${sample.count}`);
    await expect(page.locator(".pn-finding")).toHaveCount(sample.count);
    await expect(page.locator(".pn-finding mark").first()).toBeVisible();
    const stored = await page.evaluate(async () => ({
      local: localStorage.length,
      session: sessionStorage.length,
      dbs: indexedDB.databases ? (await indexedDB.databases()).length : 0,
    }));
    expect(stored).toEqual({ local: 0, session: 0, dbs: 0 });
    expect(page.url()).not.toContain("?");
    await checkA11y(page);
  });

  test("чистый текст даёт «Готово»", async ({ page }) => {
    await page.goto("check/");
    await page.getByLabel("Текст памятки, шаблона или письма").fill("Обратитесь в поликлинику по месту жительства и попросите ответ письменно.");
    await page.getByRole("button", { name: "Проверить" }).click();
    await expect(page.locator(".pn-check__result .op-status--done")).toBeVisible();
    await page.getByRole("button", { name: "Очистить" }).click();
    await expect(page.locator(".pn-check__result")).toBeHidden();
    await expect(page.getByLabel("Текст памятки, шаблона или письма")).toHaveValue("");
  });

  test("разметка в тексте не исполняется и выводится текстом", async ({ page }) => {
    await page.goto("check/");
    await page.evaluate(() => { window.__pnXss = 0; });
    const evil = "Справку выдаёт ПФР <img src=x onerror=\"window.__pnXss=1\"> <script>window.__pnXss=2</script> <b>жирный</b>";
    await page.getByLabel("Текст памятки, шаблона или письма").fill(evil);
    await page.getByRole("button", { name: "Проверить" }).click();
    await expect(page.locator(".pn-check__result")).toBeVisible();
    await page.waitForTimeout(300);
    expect(await page.evaluate(() => window.__pnXss)).toBe(0);
    await expect(page.locator(".pn-check__result img, .pn-check__result script, .pn-check__result b")).toHaveCount(0);
    const frag = (await page.locator(".pn-finding__frag").allTextContents()).join(" ");
    expect(frag).toContain("<img src=x");
    expect(frag).toContain("<script>");
  });
});
