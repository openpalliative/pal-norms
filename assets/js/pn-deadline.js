import { params } from "./pn-params.js";
import { todayIso } from "../../ui/js/format.js";
import { checkDate3, readDate3, setDate3, showDate3Error, wireDates } from "../../ui/js/date3.js";

const here = (p) => new URL(p, import.meta.url);
const load = (p) => import(here(p).href);
const narrow = () => matchMedia("(max-width: 599px)").matches;

async function json(name, whole = false) {
  const res = await fetch(here(`../../data/v1/${name}.json`));
  if (!res.ok) throw new Error(name);
  const env = await res.json();
  return whole ? env : env.items;
}

class PnDeadline extends HTMLElement {
  connectedCallback() {
    this.form = this.querySelector("form");
    this.out = this.querySelector(".pn-result");
    this.date = this.querySelector("#pn-date");
    this.querySelector(".pn-nojs").hidden = true;
    this.buildOptions();
    this.pointer = false;
    this.form.addEventListener("pointerdown", (e) => {
      this.pointer = Boolean(e.target.closest(".pn-calc__opt"));
    });
    this.form.addEventListener("keydown", () => {
      this.pointer = false;
    });
    this.form.addEventListener("change", (e) => {
      if (e.target.name === "rule") this.onRule(this.pointer);
    });
    this.form.addEventListener("submit", (e) => {
      e.preventDefault();
      this.calculate();
    });
    wireDates(this);
    this.form.hidden = false;
    this.ready = this.load();
    this.ready.catch(() => {});
    this.prefill();
    this.tidyTable();
  }

  async load() {
    const [lib, view, rules, calendar, quotes, acts] = await Promise.all([
      load("../../lib/deadlines.js"), load("./pn-result.js"),
      json("deadline-rules"), json("calendar", true), json("quotes"), json("acts"),
    ]);
    const byId = (list) => new Map(list.map((x) => [x.id, x]));
    Object.assign(this, { lib, view, calendar, rules: byId(rules), quotes: byId(quotes), acts: byId(acts) });
  }

  buildOptions() {
    const pick = this.querySelector(".pn-calc__pick");
    if (!pick) return;
    const groupTpl = pick.querySelector('template[data-tpl="group"]');
    const optTpl = pick.querySelector('template[data-tpl="opt"]');
    const err = pick.querySelector("#pn-rule-error");
    let first = true;
    for (const body of document.querySelectorAll(".pn-rule-table tbody[data-group]")) {
      const group = groupTpl.content.firstElementChild.cloneNode(true);
      const rows = body.querySelectorAll("tr[data-rule]");
      const name = group.querySelector(".pn-calc__gname");
      name.textContent = body.querySelector(".pn-rule-table__group th").textContent;
      name.id = `pn-g-${body.dataset.group}`;
      group.querySelector(".pn-calc__gcount").textContent = String(rows.length);
      const box = group.querySelector(".pn-calc__gbody");
      box.setAttribute("aria-labelledby", name.id);
      for (const row of rows) {
        const opt = optTpl.content.firstElementChild.cloneNode(true);
        for (const key of ["dir", "group"]) if (row.dataset[key]) opt.dataset[key] = row.dataset[key];
        opt.dataset.event = row.querySelector("[data-ev]").textContent;
        if ("from" in row.dataset) opt.dataset.from = "";
        opt.querySelector("input").value = row.dataset.rule;
        opt.querySelector("span").textContent = row.querySelector("th a").textContent;
        box.append(opt);
      }
      group.open = first;
      first = false;
      pick.insertBefore(group, err);
    }
  }

  tidyTable() {
    const all = document.querySelector(".pn-all-rules__details");
    if (all && narrow()) all.open = false;
  }

  option() {
    const id = this.form.elements.rule?.value || "";
    return id ? this.form.querySelector(`input[name="rule"][value="${CSS.escape(id)}"]`) : null;
  }

  onRule(advance = false) {
    const opt = this.option();
    const holder = opt?.closest("[data-event]");
    const label = this.querySelector("[data-event-label]");
    if (label && holder) label.textContent = holder.dataset.event;
    if (holder) this.date.dataset.max = holder.dataset.dir === "backward" ? "2100-12-31" : "today";
    const err = this.querySelector("#pn-rule-error");
    if (err) err.hidden = true;
    const mine = opt?.closest(".pn-calc__group");
    if (mine) {
      mine.open = true;
      if (advance) for (const g of this.querySelectorAll(".pn-calc__group")) if (g !== mine) g.open = false;
    }
    if (advance) {
      const day = this.date.querySelector('[data-part="d"]');
      requestAnimationFrame(() => {
        this.date.scrollIntoView({ block: narrow() ? "start" : "nearest", behavior: "instant" });
        day.focus({ preventScroll: true });
      });
    }
  }

  prefill() {
    const radio = params.rule && [...this.form.querySelectorAll('input[name="rule"][type="radio"]')]
      .find((r) => r.value === params.rule);
    if (radio) {
      radio.checked = true;
      this.onRule(false);
    }
    const ok = /^\d{4}-\d{2}-\d{2}$/.test(params.from || "")
      && !checkDate3(params.from.slice(8), params.from.slice(5, 7), params.from.slice(0, 4), { min: "2000-01-01", max: "today" }).error;
    if (ok && this.option()?.closest("[data-from]")) {
      setDate3(this.date, params.from);
      this.calculate();
    }
  }

  async calculate() {
    const opt = this.option();
    if (!opt) {
      const err = this.querySelector("#pn-rule-error");
      err.hidden = false;
      const group = this.querySelector(".pn-calc__group");
      if (group) group.open = true;
      this.form.querySelector('input[name="rule"]').focus();
      return;
    }
    const { iso, error } = readDate3(this.date);
    this.date.classList.toggle("op-field--error", Boolean(error));
    if (error) {
      this.date.querySelector("input, select").focus();
      return;
    }
    const today = todayIso();
    const slow = setTimeout(() => this.status("Считаем"), 300);
    try {
      await this.ready;
    } catch {
      clearTimeout(slow);
      this.status("Не получилось загрузить данные для расчёта. Обновите страницу");
      return;
    }
    clearTimeout(slow);
    const rule = this.rules.get(opt.value);
    let res;
    try {
      res = this.lib.computeDeadline({ rule, start: iso, calendar: this.calendar });
    } catch {
      showDate3Error(this.date, "Эту дату не получилось посчитать. Проверьте её");
      return;
    }
    const node = this.view.renderResult(this, rule, iso, res, today);
    this.out.replaceChildren(node);
    this.out.hidden = false;
    this.closest(".pn-deadlines")?.classList.add("has-result");
    this.out.querySelector(".pn-res__title").focus();
  }

  status(text) {
    const p = document.createElement("p");
    p.textContent = text;
    this.out.replaceChildren(p);
    this.out.hidden = false;
  }
}

if (!customElements.get("pn-deadline")) customElements.define("pn-deadline", PnDeadline);
