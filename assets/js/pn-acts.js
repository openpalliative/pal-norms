import { plural } from "../../ui/js/format.js";

const norm = (s) => s.toLowerCase().replace(/ё/g, "е").replace(/\s+/g, " ").trim();

class PnActs extends HTMLElement {
  connectedCallback() {
    this.form = this.querySelector(".pn-filter");
    this.input = this.querySelector("#pn-q");
    this.count = this.querySelector("[data-count]");
    this.empty = this.querySelector("[data-empty]");
    this.rows = [...this.querySelectorAll(".pn-act")].map((el) => ({ el, text: norm(el.querySelector(".pn-act__main").textContent) }));
    this.form.addEventListener("submit", (e) => e.preventDefault());
    this.form.addEventListener("input", () => this.apply());
    this.form.addEventListener("change", () => this.apply());
    this.form.hidden = false;
    this.enrich();
  }

  async enrich() {
    try {
      const res = await fetch(new URL("../../data/v1/acts.json", import.meta.url));
      const byId = new Map((await res.json()).items.map((a) => [a.id, a]));
      for (const row of this.rows) {
        const a = byId.get(row.el.dataset.id);
        if (a) row.text = norm(`${row.text} ${a.title} ${a.authority} ${(a.aliases || []).join(" ")}`);
      }
      if (this.input.value) this.apply();
    } catch {}
  }

  apply() {
    const words = norm(this.input.value).split(" ").filter(Boolean);
    const st = this.form.elements.st.value;
    let shown = 0;
    for (const { el, text } of this.rows) {
      const okText = words.every((w) => text.includes(w));
      const okSt = st === "all" || (st === "unverified" ? el.dataset.verified === "false" : el.dataset.status === st);
      el.hidden = !(okText && okSt);
      if (!el.hidden) shown += 1;
    }
    for (const sec of this.querySelectorAll(".pn-actgroup")) {
      sec.hidden = !sec.querySelector(".pn-act:not([hidden])");
    }
    this.empty.hidden = shown > 0;
    const filtered = words.length || st !== "all";
    this.count.textContent = filtered ? `Показано ${plural(shown, "документ", "документа", "документов")} из ${this.rows.length}` : "";
  }
}

if (!customElements.get("pn-acts")) customElements.define("pn-acts", PnActs);
