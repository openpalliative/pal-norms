import { parseIsoDate, plural, ruDate, ruDateLong } from "../../ui/js/format.js";
import { xurl } from "../../ui/js/xparams.js";

const WEEKDAYS = ["воскресенье", "понедельник", "вторник", "среда", "четверг", "пятница", "суббота"];
const PRAVO = "http://publication.pravo.gov.ru/document/";

const here = (p) => new URL(p, import.meta.url);
const load = (p) => import(here(p).href);
const pick = (root, sel) => root.querySelector(`[data-f="${sel}"]`);
const part = (root, sel) => root.querySelector(`[data-part="${sel}"]`);

export function longDate(iso) {
  const d = parseIsoDate(iso);
  return d ? `${ruDateLong(iso)}, ${WEEKDAYS[d.getUTCDay()]}` : "";
}

export function yearsWord(years) {
  if (years.length === 1) return `${years[0]} год`;
  return `${years.slice(0, -1).join(", ")} и ${years.at(-1)} годы`;
}

export function renderQuote(ctx, q) {
  const node = ctx.querySelector('template[data-tpl="quote"]').content.cloneNode(true);
  const act = ctx.acts.get(q.act_id);
  pick(node, "q-text").textContent = q.text;
  const a = pick(node, "q-act");
  if (act) {
    a.textContent = act.short_title;
    a.href = `${here(`../../acts/${act.id}/`).pathname}#${q.anchor}`;
    a.after(", ");
  } else a.remove();
  pick(node, "q-point").textContent = q.point + (q.page ? `, страница ${q.page} скана` : "");
  if (act?.eoNumber) pick(node, "q-eo").textContent = act.eoNumber;
  else part(node, "q-eo").remove();
  const link = pick(node, "q-link");
  const ips = q.text_source === "ips_archive";
  const href = ips ? act?.alt_source?.snapshot_url : act?.eoNumber && (act.url || PRAVO + act.eoNumber);
  if (href) {
    link.href = href;
    link.textContent = ips ? "Снимок текста в архиве" : "Официальная публикация";
    if (act?.eoNumber && !ips) link.title = `Номер публикации ${act.eoNumber}`;
  } else link.remove();
  if (q.verified && q.verified_at) pick(node, "q-checked").textContent = `${href ? ", сверено" : "Сверено"} со сканом ${ruDate(q.verified_at)}`;
  if (!q.verified) {
    part(node, "q-unv").hidden = false;
    pick(node, "q-unv").textContent = ips
      ? "Текста этого документа нет на портале официальной публикации. Цитата взята из базы «Законодательство России» по снимку web.archive.org и с официальным текстом не сверена"
      : "Цитата ещё не сверена со сканом официальной публикации. Уточните по ссылке";
  }
  return node;
}

export function unverifiedText(ctx, rule, iso, res) {
  const out = [];
  if (!rule.verified) out.push("Текст нормы ещё не сверен с официальной публикацией. Дата ориентировочная, проверьте по ссылке на документ");
  if (res.calendar_verified === false) {
    const known = ctx.lib.calendarYears(ctx.calendar);
    const span = [iso, res.due, res.due_alt].filter(Boolean).map((d) => +d.slice(0, 4));
    const years = [];
    for (let y = Math.min(...span); y <= Math.max(...span); y += 1) if (!known[y]?.verified) years.push(y);
    let t = `Календарь на ${years.length ? yearsWord(years) : "этот год"} ещё не утверждён. Дата может сдвинуться на несколько дней`;
    if (res.margin_applied > 0) t += `. Мы взяли запас ${plural(res.margin_applied, "рабочий день", "рабочих дня", "рабочих дней")}`;
    out.push(t);
  }
  return out.join(". ");
}

function regionalLine(d) {
  const p = document.createElement("p");
  const where = d.region_in ? d.region_in[0].toUpperCase() + d.region_in.slice(1) : `В регионе «${d.region_name}»`;
  p.append(`${where} в этот период был дополнительный нерабочий день: ${ruDateLong(d.date)}${d.title ? `, ${d.title}` : ""}. Срок может сдвинуться, толкование не проверено юристом в РФ. `);
  const href = d.eoNumber ? PRAVO + d.eoNumber : d.act_id ? here(`../../acts/${d.act_id}/`).pathname : "";
  if (href) {
    const a = document.createElement("a");
    a.href = href;
    a.textContent = d.eoNumber ? "Официальная публикация" : "Документ";
    p.append(a);
  }
  return p;
}

export async function fillRegional(slot, calendar, from, to) {
  const [{ regionalInRange }, { getRegion }] = await Promise.all([load("../../lib/regional.js"), load("../../ui/js/region-store.js")]);
  const region = getRegion();
  const mine = region ? regionalInRange(calendar, from, to, region) : [];
  const all = regionalInRange(calendar, from, to);
  if (region && mine.length) {
    slot.append(...mine.map(regionalLine));
  } else if (!region && all.length) {
    const det = document.createElement("details");
    det.className = "pn-basis";
    det.dataset.printClosed = "";
    const sum = document.createElement("summary");
    sum.textContent = `В некоторых регионах в этот период были дополнительные нерабочие дни: ${all.length}`;
    det.append(sum, ...all.map(regionalLine));
    slot.append(det);
  } else return;
  slot.hidden = false;
}

export function renderResult(ctx, rule, iso, res, today) {
  const node = ctx.querySelector('template[data-tpl="result"]').content.cloneNode(true);
  const label = rule.result_label || "Срок";
  const due = longDate(res.due);
  const show = (name, field, text) => {
    part(node, name).hidden = false;
    if (field) pick(node, field).textContent = text;
  };
  pick(node, "situation").textContent = rule.situation;
  pick(node, "label").textContent = label;
  pick(node, "due").textContent = due;
  if (res.due_alt && res.due_alt !== res.due) show("alt", "alt", longDate(res.due_alt));
  if (res.extended && rule.extension) {
    show("extended", "extended", longDate(res.extended));
    pick(node, "ext-label").textContent = rule.extension.label[0].toUpperCase() + rule.extension.label.slice(1);
  }
  if ((res.latest || res.due) < today) {
    if (rule.direction === "backward") {
      show("passed", "passed-text", "Эта дата уже прошла. Если ничего не сделали, спросите об этом письменно");
      part(node, "passed-ok").hidden = true;
      part(node, "passed-18").hidden = rule.from_event !== "turns-18";
    } else {
      const maybeExtended = res.extended && rule.extension && res.extended >= today;
      show("passed", "passed-text", maybeExtended
        ? "Дата уже прошла. Если ответа нет и вам не сообщали о продлении срока, это повод для следующего шага"
        : "Дата уже прошла. Если не выполнили, это повод для следующего шага");
      pick(node, "ok-link").href = xurl("obrashchenie-kit", "case/", { new: "1", s: "no-answer", rule: rule.id, from: iso });
    }
  }
  if (rule.group === "pharmacy") show("pain");
  const cal = Array.isArray(ctx.calendar) ? { items: ctx.calendar } : ctx.calendar;
  if ((cal?.items || []).some((i) => i.kind === "regional") || cal?.regional?.length) {
    fillRegional(part(node, "regional"), cal, iso, res.latest || res.due).catch(() => {});
  }
  if (rule.ambiguous) show("ambiguous", "note", rule.ambiguity_note || "");
  const unv = unverifiedText(ctx, rule, iso, res);
  if (unv) show("unverified", "unv-text", unv);
  if (!rule.verified) node.querySelector(".pn-res").classList.add("pn-res--unv");
  if (rule.legal_review?.status === "ok") {
    const legal = pick(node, "legal");
    legal.classList.add("pn-legal--ok");
    legal.querySelector("span").textContent = "Толкование проверил юрист в РФ";
    const ok = document.getElementById("op-icon-circle-check");
    if (ok) legal.querySelector(".op-icon").replaceWith(ok.content.cloneNode(true));
  }
  const formula = res.formula || "";
  pick(node, "formula").textContent = formula && formula[0].toUpperCase() + formula.slice(1);
  const said = new Set((formula.match(/ \([^()]+\)/g) || []));
  const short = (label) => [...said].reduce((t, p) => t.replace(p, ""), label);
  for (const s of res.steps || []) {
    const li = document.createElement("li");
    const b = document.createElement("strong");
    b.textContent = longDate(s.date);
    li.append(`${short(s.label)}: `, b);
    pick(node, "steps").append(li);
  }
  const qs = rule.quote_ids.map((id) => ctx.quotes.get(id)).filter(Boolean);
  if (qs.length) pick(node, "quotes").append(...qs.map((q) => renderQuote(ctx, q)));
  else part(node, "quotes").hidden = true;
  const ruleUrl = here(`../../deadlines/${rule.id}/`);
  const more = pick(node, "rule-link");
  if (location.pathname === ruleUrl.pathname) more.parentElement.hidden = true;
  else more.href = ruleUrl.pathname;
  const steps = (res.steps || []).map((s) => `${s.label}: ${longDate(s.date)}`).join("\n");
  const text = `${label}: ${due}.\n${steps}\nПодробнее о сроке: ${ruleUrl.href}`;
  const share = node.querySelector("op-share");
  share.dataset.text = text;
  share.querySelector('[data-share="sms"]').href = `sms:?&body=${encodeURIComponent(text)}`;
  share.querySelector('[data-share="mail"]').href = `mailto:?subject=${encodeURIComponent("Срок")}&body=${encodeURIComponent(text)}`;
  node.querySelector('[data-act="ics"]').addEventListener("click", async () => {
    const [{ buildIcs }, { downloadText }] = await Promise.all([load("../../ui/js/ics.js"), load("../../ui/js/files.js")]);
    const ics = buildIcs([{
      uid: `${rule.id}-${res.due}@openpalliative`,
      date: res.due,
      summary: `Срок: ${rule.situation}`,
      description: `${label}: ${due}. ${formula}`,
      alarmsDaysBefore: [1],
    }]);
    downloadText(ics, `srok-${res.due}.ics`, "text/calendar;charset=utf-8");
  });
  return node;
}
