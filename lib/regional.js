const ISO = /^\d{4}-\d{2}-\d{2}$/;

export function regionalDays(calendar) {
  const items = Array.isArray(calendar?.items) ? calendar.items.filter((i) => i?.kind === "regional") : [];
  const extra = Array.isArray(calendar?.regional) ? calendar.regional : [];
  const out = [];
  for (const item of [...items, ...extra]) {
    if (!item || typeof item !== "object") continue;
    const days = Array.isArray(item.days) ? item.days.map((d) => ({ ...item, ...d, days: undefined })) : [item];
    for (const d of days) {
      if (typeof d.date !== "string" || !ISO.test(d.date) || typeof d.region_id !== "string") continue;
      out.push({
        region_id: d.region_id.toUpperCase(),
        region_name: d.region_name || d.region_id,
        region_in: d.region_in || null,
        date: d.date,
        title: d.title || "",
        act_id: d.act_id || null,
        eoNumber: d.eoNumber || d.act_eoNumber || null,
        verified: d.verified === true,
      });
    }
  }
  return out.sort((a, b) => a.date.localeCompare(b.date) || a.region_id.localeCompare(b.region_id));
}

export function regionalInRange(calendar, fromIso, toIso, region = null) {
  if (!ISO.test(fromIso || "") || !ISO.test(toIso || "")) return [];
  const [a, b] = fromIso <= toIso ? [fromIso, toIso] : [toIso, fromIso];
  return regionalDays(calendar).filter((d) => d.date > a && d.date <= b && (!region || d.region_id === region.toUpperCase()));
}
