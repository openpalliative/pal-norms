import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync } from "node:fs";

const built = new URL("../../_site/assets/js/pn-result.js", import.meta.url);

test("дата словами с днём недели", { skip: !existsSync(built) }, async () => {
  const { longDate, yearsWord } = await import(built.href);
  assert.equal(longDate("2026-11-14"), "14 ноября 2026, суббота");
  assert.equal(longDate("2027-01-01"), "1 января 2027, пятница");
  assert.equal(longDate("нет"), "");
  assert.equal(yearsWord([2027]), "2027 год");
  assert.equal(yearsWord([2027, 2028]), "2027 и 2028 годы");
});

test("у каждой иконки на странице есть правило в подключённых стилях", { skip: !existsSync(new URL("../../_site/index.html", import.meta.url)) }, async () => {
  const { readFileSync, readdirSync, statSync } = await import("node:fs");
  const { join, dirname, normalize } = await import("node:path");
  const root = new URL("../../_site/", import.meta.url).pathname;
  const pages = [];
  const walk = (d) => {
    for (const n of readdirSync(d)) {
      const p = join(d, n);
      if (statSync(p).isDirectory()) walk(p);
      else if (n.endsWith(".html")) pages.push(p);
    }
  };
  walk(root);
  for (const page of pages) {
    const html = readFileSync(page, "utf8");
    const used = new Set([...html.matchAll(/pn-i--([a-z0-9-]+)/g)].map((m) => m[1]));
    let css = "";
    for (const m of html.matchAll(/<link rel="stylesheet" href="([^"]+)"/g)) {
      try { css += readFileSync(normalize(join(dirname(page), m[1])), "utf8"); } catch {}
    }
    for (const name of used) assert.ok(css.includes(`.pn-i--${name} `), `${page}: нет стиля иконки ${name}`);
  }
});

test("перенос выходного: день недели в винительном падеже", { skip: !existsSync(new URL("../../_site/calendar/2026/index.html", import.meta.url)) }, async () => {
  const { readFileSync } = await import("node:fs");
  const html = readFileSync(new URL("../../_site/calendar/2026/index.html", import.meta.url), "utf8");
  const lines = html.match(/Выходной переносится с [^<]+/g) || [];
  assert.ok(lines.length > 0);
  for (const l of lines) assert.doesNotMatch(l, / на (среда|пятница|суббота) /);
});

test("строка данных на главной и в списке документов со стилями", { skip: !existsSync(new URL("../../_site/index.html", import.meta.url)) }, async () => {
  const { readFileSync } = await import("node:fs");
  for (const p of ["index.html", "acts/index.html"]) {
    const html = readFileSync(new URL(`../../_site/${p}`, import.meta.url), "utf8");
    assert.match(html, /class="op-data-date pn-dataline__watch"/, p);
  }
  const css = readFileSync(new URL("../../_site/assets/css/pn.css", import.meta.url), "utf8");
  assert.match(css, /\.pn-dataline \{[^}]*flex-direction: column/);
});
