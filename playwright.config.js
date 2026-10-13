import { defineConfig } from "@playwright/test";

const port = 8701;
const repo = "pal-norms";
const browserName = process.env.OP_BROWSER || "chromium";
const suffix = browserName === "chromium" ? "" : `-${browserName}`;
const touch = { hasTouch: true, isMobile: browserName !== "firefox" };

export default defineConfig({
  testDir: ".",
  testMatch: ["tests/e2e/**/*.spec.js", "opsite/tests/pages.spec.js"],
  testIgnore: ["scripts/**", "node_modules/**", "vendor/**"],
  timeout: browserName === "chromium" ? 30000 : 60000,
  workers: process.env.CI ? undefined : 2,
  outputDir: `_reports/pw${suffix}`,
  reporter: [["list"], ["json", { outputFile: `_reports/e2e${suffix}.json` }]],
  use: { baseURL: `http://127.0.0.1:${port}/${repo}/`, headless: true, locale: "ru-RU", timezoneId: "Europe/Moscow" },
  webServer: {
    command: "uv run python -m opsite serve --no-open",
    url: `http://127.0.0.1:${port}/${repo}/`,
    reuseExistingServer: true,
  },
  projects: [
    { name: "desktop", use: { browserName, viewport: { width: 1440, height: 900 } } },
    { name: "mobile", use: { browserName, viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, ...touch } },
    { name: "nojs", use: { browserName, viewport: { width: 1280, height: 800 }, javaScriptEnabled: false }, grep: /@nojs/ },
    { name: "w360", use: { browserName, viewport: { width: 360, height: 640 }, ...touch }, grep: /@widths/ },
    { name: "w768", use: { browserName, viewport: { width: 768, height: 1024 }, ...touch }, grep: /@widths/ },
    { name: "w1024", use: { browserName, viewport: { width: 1024, height: 768 } }, grep: /@widths/ },
  ],
});
