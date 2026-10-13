const DAY = 86400000;

function toDate(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || "");
  if (!m) throw new RangeError(`Дата должна быть в виде ГГГГ-ММ-ДД: ${iso}`);
  const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
  if (d.getUTCMonth() !== +m[2] - 1) throw new RangeError(`Такой даты нет: ${iso}`);
  return d;
}

function toIso(d) {
  return d.toISOString().slice(0, 10);
}

export function addDays(iso, n) {
  return toIso(new Date(toDate(iso).getTime() + n * DAY));
}

function weekday(iso) {
  return toDate(iso).getUTCDay();
}

function isWeekend(iso) {
  const w = weekday(iso);
  return w === 0 || w === 6;
}

function items(calendar) {
  if (Array.isArray(calendar)) return calendar;
  return (calendar && calendar.items) || [];
}

const cache = new WeakMap();

function index(calendar) {
  const key = typeof calendar === "object" && calendar ? calendar : {};
  if (cache.has(key)) return cache.get(key);
  const list = items(calendar);
  const baseline = list.find((it) => it.kind === "baseline") || {
    holidays_mmdd: [], carry_over: false, carry_exclude_mmdd: [], verified: false,
  };
  const years = new Map();
  for (const it of list) {
    if (it.kind === "year") {
      years.set(Number(it.year), { verified: it.verified === true, off: new Set(it.off), work: new Set(it.work), item: it });
    }
  }
  const idx = { baseline, years, derived: new Map() };
  cache.set(key, idx);
  return idx;
}

function derivedYear(idx, year) {
  if (idx.derived.has(year)) return idx.derived.get(year);
  const b = idx.baseline;
  const holidays = new Set(b.holidays_mmdd.map((md) => `${year}-${md}`));
  const off = new Set(holidays);
  const exclude = new Set(b.carry_exclude_mmdd || []);
  if (b.carry_over) {
    for (const md of b.holidays_mmdd) {
      const iso = `${year}-${md}`;
      if (exclude.has(md) || !isWeekend(iso)) continue;
      let d = addDays(iso, 1);
      while (isWeekend(d) || off.has(d)) d = addDays(d, 1);
      off.add(d);
    }
  }
  const y = { verified: false, off, work: new Set(), derived: true };
  idx.derived.set(year, y);
  return y;
}

function yearInfo(idx, year) {
  return idx.years.get(year) || derivedYear(idx, year);
}

export function isWorkingDay(iso, calendar) {
  const idx = index(calendar);
  const y = yearInfo(idx, toDate(iso).getUTCFullYear());
  let working;
  if (y.work.has(iso)) working = true;
  else if (y.off.has(iso)) working = false;
  else working = !isWeekend(iso);
  return { working, verified: y.verified };
}

export function addWorkingDays(iso, n, calendar) {
  const step = n < 0 ? -1 : 1;
  let left = Math.abs(n);
  let d = iso;
  while (left > 0) {
    d = addDays(d, step);
    if (isWorkingDay(d, calendar).working) left -= 1;
  }
  return d;
}

export function nextWorkingDay(iso, calendar) {
  let d = iso;
  while (!isWorkingDay(d, calendar).working) d = addDays(d, 1);
  return d;
}

export function nonWorkingDays(fromIso, toIso_, calendar) {
  const idx = index(calendar);
  const out = [];
  for (let d = fromIso; d <= toIso_; d = addDays(d, 1)) {
    if (isWorkingDay(d, calendar).working) continue;
    const md = d.slice(5);
    let kind = "weekend";
    if (idx.baseline.holidays_mmdd.includes(md)) kind = "holiday";
    else if (!isWeekend(d)) kind = "transfer";
    out.push({ date: d, kind });
  }
  return out;
}

export function calendarYears(calendar) {
  const out = {};
  for (const [year, y] of index(calendar).years) out[year] = { verified: y.verified };
  return out;
}

function rangeVerified(a, b, calendar) {
  const idx = index(calendar);
  const lo = Math.min(toDate(a).getUTCFullYear(), toDate(b).getUTCFullYear());
  const hi = Math.max(toDate(a).getUTCFullYear(), toDate(b).getUTCFullYear());
  for (let y = lo; y <= hi; y += 1) if (!yearInfo(idx, y).verified) return false;
  return true;
}

function plural(n, one, few, many) {
  const a = Math.abs(n) % 100;
  const b = a % 10;
  if (a > 10 && a < 20) return many;
  if (b === 1) return one;
  if (b > 1 && b < 5) return few;
  return many;
}

export function unitWords(value, unit) {
  if (unit === "within_24h") return "в течение суток";
  const adj = unit === "working_days"
    ? plural(value, "рабочий", "рабочих", "рабочих")
    : plural(value, "календарный", "календарных", "календарных");
  return `${value} ${adj} ${plural(value, "день", "дня", "дней")}`;
}

function shift(due, unit, value, calendar) {
  if (unit === "within_24h") return addDays(due, 1);
  if (unit === "working_days") return addWorkingDays(due, value, calendar);
  return addDays(due, value);
}

export function formulaOf(rule) {
  if (rule.direction === "backward") {
    const s = `не позже чем за ${unitWords(rule.value, rule.unit)} до события`;
    return rule.margin_working_days ? `${s}, с запасом, если календарь не утверждён` : s;
  }
  const parts = [unitWords(rule.value, rule.unit)];
  if (rule.pre) parts.push(`${unitWords(rule.pre.value, rule.pre.unit)} ${rule.pre.label}`);
  if (rule.shift_if_nonworking === "yes") parts.push("срок, который выпал на нерабочий день, переносится на следующий рабочий");
  return parts.join(", ");
}

export function computeDeadline({ rule, start, calendar }) {
  toDate(start);
  const steps = [{ label: rule.from_event_label, date: start }];
  let due;
  let dueAlt = null;
  let margin = 0;
  let base = start;
  if (rule.direction === "backward") {
    if (rule.unit !== "working_days") due = addDays(start, -rule.value);
    else due = addWorkingDays(start, -rule.value, calendar);
    steps.push({ label: `За ${unitWords(rule.value, rule.unit)} до события`, date: due });
    if (rule.margin_working_days > 0 && !rangeVerified(due, start, calendar)) {
      margin = rule.margin_working_days;
      due = addWorkingDays(due, -margin, calendar);
      steps.push({ label: `С запасом ${unitWords(margin, "working_days")}`, date: due });
    }
  } else {
    if (rule.pre) {
      base = shift(start, rule.pre.unit, rule.pre.value, calendar);
      steps.push({ label: `Не позже, чем через ${unitWords(rule.pre.value, rule.pre.unit)} ${rule.pre.label}`, date: base });
    }
    due = shift(base, rule.unit, rule.value, calendar);
    steps.push({ label: rule.unit === "within_24h" ? "В течение суток" : `Через ${unitWords(rule.value, rule.unit)}`, date: due });
    const shifted = nextWorkingDay(due, calendar);
    if (shifted !== due) {
      if (rule.shift_if_nonworking === "yes") {
        steps.push({ label: "Срок выпал на нерабочий день и переносится на следующий рабочий", date: shifted });
        due = shifted;
      } else if (rule.shift_if_nonworking === "unknown") {
        dueAlt = shifted;
        steps.push({ label: "Если срок переносится с нерабочего дня", date: shifted });
      }
    }
  }
  const latest = dueAlt && dueAlt > due ? dueAlt : due;
  const extended = rule.extension && rule.direction !== "backward"
    ? shift(latest, rule.extension.unit, rule.extension.value, calendar)
    : null;
  const lo = due < start ? due : start;
  const hi = (extended || latest) > start ? (extended || latest) : start;
  return {
    rule_id: rule.id,
    due,
    due_alt: dueAlt,
    latest,
    extended,
    formula: formulaOf(rule),
    steps,
    norm_ids: rule.norm_ids || [],
    ambiguous: rule.ambiguous === true,
    verified: rule.verified === true,
    calendar_verified: rangeVerified(lo, hi, calendar),
    margin_applied: margin,
  };
}
