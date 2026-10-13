import { todayIso } from "../../ui/js/format.js";

class PnHolidays extends HTMLElement {
  connectedCallback() {
    const today = todayIso();
    let shown = 0;
    for (const li of this.querySelectorAll("li[data-end]")) {
      const on = li.dataset.end >= today && shown < 4;
      li.hidden = !on;
      if (on) shown += 1;
    }
    this.querySelector(".pn-next__empty").hidden = shown > 0;
  }
}

if (!customElements.get("pn-holidays")) customElements.define("pn-holidays", PnHolidays);
