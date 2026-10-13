import { test, expect, checkA11y } from "../../opsite/tests/fixtures.js";
import { items } from "./helpers.js";

const acts = items("acts");
const quotes = items("quotes");
const repealed = acts.filter((a) => a.status === "repealed");
const withQuote = acts.find((a) => a.id === "208n-243n" && a.quote_ids.length) || acts.find((a) => a.quote_ids.length);

test.describe("Документы", () => {
  for (const word of ["МСЭ", "ТСР", "ВК"]) {
    test(`поиск «${word}» находит документы`, async ({ page }, info) => {
      test.skip(info.project.name === "nojs");
      await page.goto("acts/");
      await page.getByLabel("Найти документ").fill(word);
      await expect(page.locator(".pn-act:not([hidden])").first()).toBeVisible();
      await expect(page.locator("[data-empty]")).toBeHidden();
      await expect(page.locator("[data-count]")).toContainText("Показано");
    });
  }

  test("страница акта: реквизиты под заголовком, статус без пустой рамки", async ({ page }, info) => {
    test.skip(info.project.name === "nojs");
    const a = acts.find((x) => x.id === "505n") || acts.find((x) => x.status === "in_force" && x.kind === "ministry_order");
    test.skip(!a);
    await page.goto(`acts/${a.id}/`);
    const req = page.locator("h1 + .pn-actpage__req");
    await expect(req).toContainText(`от ${a.doc_date.split("-").reverse().join(".")} № ${a.number}`);
    if (a.id === "505n") await expect(req).toHaveText("Приказ Минздрава России от 10.07.2019 № 505н");
    await expect(page.locator(".pn-actpage__official")).toContainText(a.title.slice(0, 20));
    const box = page.locator(".pn-statusbox");
    await expect(box).toContainText("Действует");
    if (!a.status_basis && !a.superseded_by.length) {
      expect(await box.evaluate((el) => getComputedStyle(el).borderTopStyle)).toBe("none");
    }
    await expect(page.locator(".op-draft")).toBeVisible();
    await checkA11y(page);
  });

  test("«Утратил силу» пунктиром, иконкой и словом, не красным", async ({ page }, info) => {
    test.skip(info.project.name === "nojs" || !repealed.length);
    await page.goto(`acts/${repealed[0].id}/`);
    const badge = page.locator(".pn-act-status--repealed").first();
    await expect(badge).toContainText("Утратил силу");
    await expect(badge.locator(".op-icon")).toHaveCount(1);
    const [icon, danger, border] = await badge.evaluate((el) => {
      const probe = document.createElement("span");
      probe.style.color = "var(--op-danger)";
      document.body.append(probe);
      const out = [getComputedStyle(el.querySelector(".op-icon")).backgroundColor, getComputedStyle(probe).color, getComputedStyle(el).borderTopStyle];
      probe.remove();
      return out;
    });
    expect(icon).not.toBe(danger);
    expect(border).toBe("dashed");
  });

  test("п. 25 на странице Положения один раз, в «Связях» якорем", async ({ page }, info) => {
    test.skip(info.project.name === "nojs" || !acts.some((a) => a.id === "208n-243n"));
    await page.goto("acts/208n-243n/");
    const q = quotes.find((x) => x.id === "208n-243n-p25");
    test.skip(!q);
    await expect(page.locator("blockquote", { hasText: q.text.slice(0, 40) })).toHaveCount(1);
    await expect(page.locator(`.pn-citerep a[href="#${q.anchor}"]`)).toHaveCount(1);
  });

  test("на телефоне реквизиты не выше 360px, статус в первом экране @widths", async ({ page }, info) => {
    test.skip(info.project.name !== "w360");
    for (const a of acts.filter((x) => ["505n", "208n-243n", "345n-372n", "59-fz"].includes(x.id))) {
      await page.goto(`acts/${a.id}/`);
      await expect(page.locator(".pn-statusbox__main")).toBeInViewport();
      const h = (await page.locator(".pn-req").boundingBox()).height;
      expect(h, a.id).toBeLessThanOrEqual(360);
      await expect(page.locator(".pn-req dt").first()).toBeVisible();
    }
  });

  test("на списке документов строка черновика и группа «Изделия и питание»", async ({ page }) => {
    await page.goto("acts/");
    await expect(page.locator(".op-draft")).toBeVisible();
    if (acts.some((a) => (a.topics || []).includes("devices"))) {
      await expect(page.getByRole("heading", { name: "Изделия и питание" })).toBeVisible();
    }
  });

  test("фильтр «Утратили силу» оставляет отменённые", async ({ page }, info) => {
    test.skip(info.project.name === "nojs");
    await page.goto("acts/");
    await page.getByRole("radio", { name: "Утратили силу" }).check();
    const visible = page.locator(".pn-act:not([hidden])");
    await expect(visible).toHaveCount(repealed.length);
    for (const a of repealed) await expect(page.locator(`.pn-act:not([hidden]) .pn-act__title[href$="acts/${a.id}/"]`)).toHaveCount(1);
    await page.getByRole("radio", { name: "Все" }).check();
    await expect(visible).toHaveCount(acts.length);
    await page.getByLabel("Найти документ").fill("такого документа точно нет");
    await expect(page.locator("[data-empty]")).toBeVisible();
    await checkA11y(page);
  });

  test("без JS виден полный список @nojs", async ({ page }, info) => {
    test.skip(info.project.name !== "nojs");
    await page.goto("acts/");
    await expect(page.locator(".pn-act")).toHaveCount(acts.length);
    await expect(page.locator(".pn-filter")).toBeHidden();
  });

  test("якорь пункта прокручивает к цитате", async ({ page }, info) => {
    test.skip(info.project.name === "nojs" || !withQuote);
    const q = quotes.find((x) => x.id === withQuote.quote_ids.at(-1));
    await page.goto(`acts/${withQuote.id}/#${q.anchor}`);
    await expect(page.locator(`#${q.anchor}`)).toBeInViewport();
    const links = page.locator("a.pn-ext");
    const n = await links.count();
    for (let i = 0; i < n; i += 1) {
      const href = await links.nth(i).getAttribute("href");
      expect(href).toMatch(/^https?:\/\/(publication\.pravo\.gov\.ru|web\.archive\.org|example\.invalid)\//);
    }
  });

  test("отменённый акт показывает замену и основание", async ({ page }, info) => {
    test.skip(info.project.name === "nojs" || !repealed.length);
    const a = repealed[0];
    await page.goto(`acts/${a.id}/`);
    await expect(page.locator(".pn-statusbox")).toContainText("Утратил силу");
    if (a.superseded_by.length) await expect(page.locator(".pn-statusbox__rel")).toContainText("Заменён");
    await checkA11y(page);
  });
});
