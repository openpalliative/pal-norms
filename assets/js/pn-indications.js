const narrow = () => matchMedia("(max-width: 599px)").matches;

class PnIndications extends HTMLElement {
  connectedCallback() {
    const field = this.querySelector(".pn-ind__filter");
    const select = this.querySelector("select");
    const groups = [...this.querySelectorAll("details[data-group]")];
    if (!field || !select || groups.length < 2) return;
    select.value = "";
    const apply = () => {
      const id = select.value;
      for (const g of groups) {
        const on = !id || g.dataset.group === id;
        g.hidden = !on;
        if (id && on) g.open = true;
        else if (!id) g.open = !narrow();
      }
    };
    select.addEventListener("change", apply);
    field.hidden = false;
    if (narrow()) apply();
  }
}

if (!customElements.get("pn-indications")) customElements.define("pn-indications", PnIndications);
