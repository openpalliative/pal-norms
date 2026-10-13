import { params } from "./pn-params.js";

class PnBack extends HTMLElement {
  async connectedCallback() {
    const id = params.back;
    if (!id || !/^[a-z0-9-]{1,40}$/.test(id)) return;
    const link = this.querySelector("a");
    const hub = new URL(link.getAttribute("href"), location.href);
    let item = null;
    try {
      const res = await fetch(new URL("situations.json", hub));
      if (res.ok) item = (await res.json()).find((s) => s.id === id) || null;
    } catch {}
    if (!item) return;
    link.href = new URL(`s/${id}/`, hub).pathname;
    this.querySelector("[data-back-title]").textContent = item.title;
    this.hidden = false;
  }
}

if (!customElements.get("pn-back")) customElements.define("pn-back", PnBack);

const opened = [];
window.addEventListener("beforeprint", () => {
  for (const d of document.querySelectorAll("main details:not([open]):not([data-print-closed])")) {
    if (d.closest("[hidden]")) continue;
    d.open = true;
    opened.push(d);
  }
});
window.addEventListener("afterprint", () => {
  while (opened.length) opened.pop().open = false;
});
