import { plural } from "../../ui/js/format.js";

const load = (p) => import(new URL(p, import.meta.url).href);

async function loadJson(name) {
  const res = await fetch(new URL(`../../data/v1/${name}.json`, import.meta.url));
  if (!res.ok) throw new Error(`${name}: ${res.status}`);
  return res.json();
}

const pick = (root, sel) => root.querySelector(`[data-f="${sel}"]`);
const part = (root, sel) => root.querySelector(`[data-part="${sel}"]`);

export function markFragment(context, fragment) {
  const frags = (Array.isArray(fragment) ? fragment : [fragment]).filter(Boolean);
  const text = context || frags.join(" ");
  const hits = [];
  for (const fr of frags) {
    let from = 0;
    let k;
    while ((k = text.indexOf(fr, from)) >= 0) {
      let e = k + fr.length;
      while (/\p{L}/u.test(fr.slice(-1)) && e < text.length && /\p{L}/u.test(text[e])) e += 1;
      if (!hits.some(([a, b]) => k < b && e > a)) hits.push([k, e]);
      from = k + fr.length;
    }
  }
  if (!hits.length) {
    const m = document.createElement("mark");
    m.textContent = frags.join(", ") || text;
    return [m];
  }
  hits.sort((a, b) => a[0] - b[0]);
  const nodes = [];
  const first = hits[0][0];
  const cut = Math.max(0, first - 60);
  if (first > 0) nodes.push((cut > 0 ? "..." : "") + text.slice(cut, first));
  hits.forEach(([a, b], n) => {
    const m = document.createElement("mark");
    m.textContent = text.slice(a, b);
    nodes.push(m);
    const next = n + 1 < hits.length ? hits[n + 1][0] : null;
    if (next !== null) nodes.push(text.slice(b, next));
  });
  const end = hits[hits.length - 1][1];
  const after = text.slice(end, end + 60);
  if (after) nodes.push(after + (end + 60 < text.length ? "..." : ""));
  return nodes;
}

export function groupFindings(found) {
  const out = [];
  const seen = new Map();
  for (const f of found) {
    const key = `${f.rule_id}:${f.line}`;
    const g = seen.get(key);
    if (g) {
      if (!g.fragments.includes(f.fragment)) g.fragments.push(f.fragment);
      continue;
    }
    const n = { ...f, fragments: [f.fragment] };
    seen.set(key, n);
    out.push(n);
  }
  return out;
}

class PnCheck extends HTMLElement {
  async connectedCallback() {
    this.form = this.querySelector("form");
    this.out = this.querySelector(".pn-check__result");
    this.area = this.querySelector("textarea");
    try {
      const [lib, view, rules, acts, quotes] = await Promise.all([
        load("../../lib/textcheck.js"), load("./pn-result.js"), loadJson("lint-rules"), loadJson("acts"), loadJson("quotes"),
      ]);
      this.lib = lib;
      this.view = view;
      this.rules = rules.items;
      this.actList = acts.items;
      this.acts = new Map(acts.items.map((a) => [a.id, a]));
      this.quotes = new Map(quotes.items.map((q) => [q.id, q]));
    } catch {
      this.show(this.tpl("error"));
      return;
    }
    this.querySelector(".pn-nojs").hidden = true;
    this.form.addEventListener("submit", (e) => {
      e.preventDefault();
      this.run();
    });
    this.form.addEventListener("reset", () => {
      this.out.replaceChildren();
      this.out.hidden = true;
      this.area.focus();
    });
    this.form.hidden = false;
  }

  tpl(name) {
    return this.querySelector(`template[data-tpl="${name}"]`).content.cloneNode(true);
  }

  show(node) {
    this.out.replaceChildren(node);
    this.out.hidden = false;
  }

  run() {
    const text = this.area.value;
    if (!text.trim()) {
      this.area.focus();
      return;
    }
    const found = groupFindings(this.lib.checkText(text, this.rules, { acts: this.actList }));
    if (!found.length) {
      const node = this.tpl("done");
      pick(node, "n").textContent = plural(this.rules.length, "правило", "правила", "правил");
      this.show(node);
      return;
    }
    const node = this.tpl("found");
    pick(node, "count").textContent = `Найдено: ${found.length}`;
    const list = pick(node, "list");
    for (const f of found) list.append(this.finding(f));
    this.show(node);
    this.out.querySelector("[data-f=count]").focus();
  }

  finding(f) {
    const node = this.tpl("finding");
    const kind = f.severity === "error" ? "error" : "warning";
    part(node, kind).hidden = false;
    pick(part(node, kind), "message").textContent = f.message;
    pick(node, "line").textContent = String(f.line);
    pick(node, "fragment").append(...markFragment(f.context, f.fragments));
    const act = f.suggest_act_id && this.acts.get(f.suggest_act_id);
    if (act) {
      const a = pick(node, "suggest");
      a.textContent = act.short_title;
      a.href = new URL(`../../acts/${act.id}/`, import.meta.url).pathname;
      part(node, "suggest").hidden = false;
    }
    const qs = (f.quote_ids || []).map((id) => this.quotes.get(id)).filter(Boolean);
    if (qs.length) {
      pick(node, "quotes").append(...qs.map((q) => this.view.renderQuote(this, q)));
      part(node, "basis").hidden = false;
    }
    return node;
  }
}

if (!customElements.get("pn-check")) customElements.define("pn-check", PnCheck);
