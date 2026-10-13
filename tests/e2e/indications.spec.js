import { mkdtempSync, symlinkSync, readFileSync, readdirSync, rmSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { spawnSync } from "node:child_process";
import { test, expect } from "../../opsite/tests/fixtures.js";
import { root } from "./helpers.js";

test.describe("Показания", () => {
  test("без JS раскрыты все группы @nojs", async ({ page }, info) => {
    test.skip(info.project.name !== "nojs");
    await page.goto("indications/");
    await expect(page.locator(".op-draft")).toBeVisible();
    const groups = page.locator("details.pn-ind__group");
    const n = await groups.count();
    for (let i = 0; i < n; i += 1) await expect(groups.nth(i)).toHaveAttribute("open", "");
    await expect(page.locator(".pn-ind__filter")).toBeHidden();
  });

  test("выбор группы не меняет адрес и историю", async ({ page }, info) => {
    test.skip(info.project.name === "nojs");
    await page.goto("indications/");
    await expect(page.locator(".op-draft")).toContainText("юристом");
    await expect(page.locator(".op-draft")).toContainText("медиком");
    const groups = page.locator("details.pn-ind__group");
    test.skip((await groups.count()) < 2, "меньше двух групп");
    const href = page.url();
    const len = await page.evaluate(() => history.length);
    const select = page.getByLabel("Показать одну группу");
    const second = await select.locator("option").nth(2).getAttribute("value");
    await select.selectOption(second);
    await expect(page.locator(`details[data-group="${second}"]`)).toBeVisible();
    await expect(page.locator("details.pn-ind__group:not([hidden])")).toHaveCount(1);
    expect(page.url()).toBe(href);
    expect(await page.evaluate(() => history.length)).toBe(len);
    expect(await page.evaluate(() => localStorage.length)).toBe(0);
    await select.selectOption("");
    await expect(page.locator("details.pn-ind__group:not([hidden])")).toHaveCount(await groups.count());
  });

  test("короткие названия групп, дословное название внутри", async ({ page }, info) => {
    test.skip(info.project.name === "nojs");
    await page.goto("indications/");
    const g = page.locator('details[data-group="a1-p6"]');
    test.skip(!(await g.count()), "нет группы п. 6");
    await expect(g.locator("summary")).toHaveText("Болезни сердца и сосудов");
    await g.evaluate((d) => { d.open = true; });
    await expect(g.locator(".pn-ind__gtitle [data-verbatim]")).toContainText("при болезнях органов кровообращения");
    const cite = g.locator(".pn-ind__cite").first();
    await expect(cite).toContainText(/страниц[аы] \d+(, \d+)* скана\.\s+Официальная публикация, сверено со сканом \d\d\.\d\d\.\d{4}/);
    await expect(cite.locator(".op-cite__eo")).toBeHidden();
    const lines = await cite.evaluate((el) => Math.round(el.getBoundingClientRect().height / parseFloat(getComputedStyle(el).lineHeight)));
    if (info.project.name === "desktop") expect(lines).toBeLessThanOrEqual(2);
  });

  test("на телефоне группы свёрнуты, кроме выбранной, высота до 9000px", async ({ page }, info) => {
    test.skip(info.project.name !== "mobile");
    await page.goto("indications/");
    const groups = page.locator("details.pn-ind__group");
    await expect(page.locator("details.pn-ind__group[open]")).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollHeight)).toBeLessThanOrEqual(9000);
    const select = page.getByLabel("Показать одну группу");
    const id = await select.locator("option").nth(1).getAttribute("value");
    await select.selectOption(id);
    await expect(page.locator(`details[data-group="${id}"]`)).toHaveAttribute("open", "");
    await expect(groups.and(page.locator(":not([hidden])"))).toHaveCount(1);
  });

  test("на Pages при закрытых воротах собирается заглушка", async ({}, info) => {
    test.skip(info.project.name !== "desktop");
    test.skip(/indications_public:\s*true/.test(readFileSync(join(root, "content", "gates.yaml"), "utf8")), "ворота открыты");
    const tmp = mkdtempSync(join(tmpdir(), "pn-gate-"));
    try {
      for (const name of readdirSync(root)) {
        if (["_site", "_reports", "node_modules", ".venv"].includes(name)) continue;
        symlinkSync(join(root, name), join(tmp, name));
      }
      const r = spawnSync("uv", ["run", "--project", process.env.PN_PROJECT || root, "python", "-m", "opsite", "--root", tmp, "build"], {
        env: { ...process.env, OP_TARGET: "pages" }, encoding: "utf8",
      });
      expect(r.status, r.stderr).toBe(0);
      const html = readFileSync(join(tmp, "_site", "indications", "index.html"), "utf8");
      expect(html).toContain("Страница ждёт проверки медиком и юристом в РФ");
      expect(html).not.toContain("pn-ind__group");
      expect(html).toContain("data/v1/indications.json");
    } finally {
      rmSync(tmp, { recursive: true, force: true });
    }
  });
});
