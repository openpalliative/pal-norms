import { existsSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { test, expect } from "../../opsite/tests/fixtures.js";
import { items, root } from "./helpers.js";

const steps = items("escalation");
const ok = join(root, "..", "obrashchenie-kit");

function okPageExists(rel) {
  if (existsSync(join(ok, "_site", "build.json")) && existsSync(join(ok, "_site", rel, "index.html"))) return true;
  const parts = rel.replace(/\/$/, "").split("/");
  if (parts[0] === "scenarios") return existsSync(join(ok, "content", "scenarios", `${parts[1]}.md`));
  if (parts[0] === "docs") return existsSync(join(ok, "data", "pack")) && JSON.stringify(readdirSync(join(ok, "data", "pack"), { recursive: true })).includes(parts[1]);
  return existsSync(join(ok, "templates", "pages", `${parts[0] || "index"}.html.j2`));
}

test.describe("Если не ответили", () => {
  test("каждая кнопка «Собрать...» ведёт на существующую страницу ok", async ({ page }, info) => {
    test.skip(info.project.name !== "desktop");
    test.skip(!existsSync(ok), "нет репо obrashchenie-kit рядом");
    await page.goto("escalation/");
    const buttons = page.locator(".pn-step__actions a", { hasText: "Собрать" });
    const n = await buttons.count();
    expect(n).toBe(steps.length);
    for (let i = 0; i < n; i += 1) {
      const href = await buttons.nth(i).getAttribute("href");
      const url = new URL(href, page.url());
      expect(url.pathname.startsWith("/obrashchenie-kit/"), href).toBe(true);
      const rel = url.pathname.replace(/^\/obrashchenie-kit\//, "");
      expect(okPageExists(rel), href).toBe(true);
    }
  });

  test("у каждой ступени видна пометка о толковании", async ({ page }) => {
    await page.goto("escalation/");
    for (const s of steps) {
      await expect(page.locator(`#${s.id}`)).toContainText(s.legal_review?.status === "ok" ? "проверил юрист" : "Толкование не проверено юристом в РФ");
    }
  });
});
