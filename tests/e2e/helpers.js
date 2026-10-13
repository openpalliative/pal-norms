import { readFileSync, existsSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

export const root = process.cwd();

export function items(name) {
  const p = join(root, "_site", "data", "v1", `${name}.json`);
  return existsSync(p) ? JSON.parse(readFileSync(p, "utf8")).items : [];
}

export function envelope(name) {
  return JSON.parse(readFileSync(join(root, "_site", "data", "v1", `${name}.json`), "utf8"));
}

export async function lib(name) {
  return import(pathToFileURL(join(root, "lib", name)).href);
}

export function isoToday() {
  const d = new Date(new Date().toLocaleString("en-US", { timeZone: "Europe/Moscow" }));
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function shiftIso(iso, days) {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

export function goldenLint() {
  const dir = join(root, "tests", "golden", "lint");
  if (!existsSync(dir)) return null;
  const txt = readdirSync(dir).filter((f) => f.endsWith(".txt")).sort();
  for (const f of txt) {
    const exp = join(dir, f.replace(/\.txt$/, ".expected.json"));
    if (!existsSync(exp)) continue;
    const expected = JSON.parse(readFileSync(exp, "utf8"));
    const list = Array.isArray(expected) ? expected : expected.findings || [];
    if (list.length) return { text: readFileSync(join(dir, f), "utf8"), count: new Set(list.map((x) => `${x.rule_id}:${x.line}`)).size };
  }
  return null;
}

export async function pickRule(page, id) {
  const radio = page.locator(`input[name="rule"][value="${id}"]`);
  if (!(await radio.count())) return;
  if (!(await radio.isVisible())) await radio.locator("xpath=ancestor::details[1]/summary").click();
  await radio.check();
  await page.evaluate(() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done))));
}

export async function fillDate(page, iso) {
  const [y, m, d] = iso.split("-");
  await page.locator("#pn-date-d").fill(String(Number(d)));
  await page.locator("#pn-date-m").selectOption(String(Number(m)));
  await page.locator("#pn-date-y").fill(y);
}

export async function calc(page, rule, start) {
  await pickRule(page, rule.id);
  await fillDate(page, start);
  await page.getByRole("button", { name: "Посчитать" }).click();
}

export async function hubSituations(page) {
  const body = readFileSync(join(root, "opsite", "situations.json"), "utf8");
  await page.route("**/situations.json", (route) => route.fulfill({ status: 200, contentType: "application/json", body }));
}

export async function printPages(page, browserName) {
  if (browserName === "chromium") {
    const buf = await page.pdf({ format: "A4", preferCSSPageSize: true, printBackground: false });
    return (buf.toString("latin1").match(/\/Type\s*\/Page[^s]/g) || []).length;
  }
  const size = page.viewportSize();
  await page.setViewportSize({ width: 703, height: 1032 });
  await page.emulateMedia({ media: "print" });
  await page.evaluate(() => window.dispatchEvent(new Event("beforeprint")));
  const h = await page.evaluate(() => document.documentElement.scrollHeight);
  await page.emulateMedia({ media: null });
  await page.setViewportSize(size);
  return Math.ceil(h / 1032);
}
