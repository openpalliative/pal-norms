import { test, expect } from "../../opsite/tests/fixtures.js";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { items, root, printPages } from "./helpers.js";

const years = items("calendar").filter((c) => c.kind === "year").map((c) => c.year);
const next = years.length ? Math.max(...years) + 1 : null;
const changes = items("changes");

test.describe("Календарь и лента", () => {
  test("следующий год без постановления: страница со статусом и основанием", async ({ page }) => {
    test.skip(!next, "нет лет в календаре");
    await page.goto(`calendar/${next}/`);
    await expect(page.locator("h1")).toHaveText(`Нерабочие дни в ${next} году`);
    await expect(page.locator(".op-status--unverified").first()).toContainText(`Календарь на ${next} год ещё не утверждён`);
    await expect(page.getByRole("link", { name: "статье 112 Трудового кодекса" })).toBeVisible();
    await page.goto("calendar/");
    await expect(page.locator(`a[href$="calendar/${next}/"]`)).toContainText("Ещё не утверждён");
  });

  test("календарь 2027 печатается на одном листе A4", async ({ page, browserName }, info) => {
    test.skip(info.project.name !== "desktop" || !years.includes(2027));
    await page.goto("calendar/2027/");
    expect(await printPages(page, browserName)).toBe(1);
  });

  test("лента Atom: валидная, по числу записей, со ссылкой со страницы", async ({ page, request }) => {
    await page.goto("changes/");
    const href = await page.locator('link[rel="alternate"][type="application/atom+xml"]').getAttribute("href");
    expect(href).toBeTruthy();
    const res = await request.get(new URL(href, page.url()).href);
    expect(res.status()).toBe(200);
    const xml = await res.text();
    const doc = await page.evaluate((x) => {
      const d = new DOMParser().parseFromString(x, "application/xml");
      return { error: d.getElementsByTagName("parsererror").length, root: d.documentElement.namespaceURI, entries: d.getElementsByTagName("entry").length, ext: [...d.querySelectorAll("link")].map((l) => l.getAttribute("href")) };
    }, xml);
    expect(doc.error).toBe(0);
    expect(doc.root).toBe("http://www.w3.org/2005/Atom");
    expect(doc.entries).toBe(changes.length);
    for (const h of doc.ext) expect(h).toMatch(/^https?:\/\/(openpalliative\.github\.io|publication\.pravo\.gov\.ru)\//);
    const file = readFileSync(join(root, "_site", "changes", "changes.xml"), "utf8");
    expect(file).not.toMatch(/<script|<img/);
  });
});
