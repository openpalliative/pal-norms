import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test, expect } from "../../opsite/tests/fixtures.js";
import { root } from "./helpers.js";

const pages = JSON.parse(readFileSync(join(root, "tests", "e2e", "pages.json"), "utf8"));

test.describe("Вёрстка на всех ширинах", () => {
  for (const p of pages) {
    test(`${p.name}: без прокрутки вбок, один заголовок @widths`, async ({ page }) => {
      await page.goto(p.path);
      await expect(page.locator("h1")).toHaveCount(1);
      const over = await page.evaluate(() => {
        const vw = document.documentElement.clientWidth;
        const wide = [...document.querySelectorAll("main *")]
          .filter((el) => !el.closest(".op-table-wrap, pre, [hidden]"))
          .filter((el) => el.getBoundingClientRect().right > vw + 1)
          .slice(0, 3)
          .map((el) => `${el.tagName.toLowerCase()}.${el.className}`);
        return { scroll: document.documentElement.scrollWidth - vw, wide };
      });
      expect(over.scroll, `прокрутка вбок: ${over.wide.join(", ")}`).toBeLessThanOrEqual(1);
      expect(over.wide).toEqual([]);
    });
  }
});
