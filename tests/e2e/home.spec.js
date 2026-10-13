import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test, expect } from "../../opsite/tests/fixtures.js";
import { items, root, hubSituations } from "./helpers.js";

const quotes = items("quotes");
const unverified = quotes.filter((q) => !q.verified).length;
const scan = quotes.filter((q) => q.verified && q.text_source === "official_pdf").length;

for (const path of ["", "data/"]) {
  test(`«Откуда эти данные» на /${path} говорит правду`, async ({ page }) => {
    await page.goto(path);
    const box = page.locator("section", { has: page.getByRole("heading", { name: "Откуда эти данные" }) });
    await expect(box).toBeVisible();
    await expect(box).not.toContainText(/кажд/i);
    await expect(box.locator('[data-count="scan"]')).toHaveText(String(scan));
    await expect(box.locator('[data-count="unverified"]')).toHaveText(String(unverified));
    if (unverified) await expect(box.locator('a[href$="data/#unverified"]')).toBeVisible();
    if (quotes.some((q) => q.text_source === "ips_archive" && !q.verified)) await expect(box).toContainText("web.archive.org");
  });
}

test("«Вернуться» берёт одно название из situations.json", async ({ page }, info) => {
  test.skip(info.project.name === "nojs");
  const html = readFileSync(join(root, "_site", "acts", "index.html"), "utf8");
  expect(html).not.toContain("data-id=\"night-pain\"");
  await hubSituations(page);
  await page.goto("acts/#back=night-pain");
  await expect(page.locator(".pn-back")).toBeVisible();
  await expect(page.locator(".pn-back")).toContainText("Сильная боль ночью");
  await page.goto("calendar/#back=no-such-situation");
  await expect(page.locator(".pn-back")).toBeHidden();
});
