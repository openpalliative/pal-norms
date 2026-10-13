export function normalize(text) {
  return String(text ?? "")
    .normalize("NFC")
    .replace(/\r\n?/g, "\n")
    .replace(/[   \t]/g, " ")
    .replace(/№[ ]*/g, "№ ");
}

function compile(pattern, flags) {
  return new RegExp(pattern, `gu${flags || ""}`);
}

function lineInfo(text, index) {
  const before = text.slice(0, index);
  const line = before.split("\n").length;
  const lineStart = before.lastIndexOf("\n") + 1;
  let lineEnd = text.indexOf("\n", index);
  if (lineEnd === -1) lineEnd = text.length;
  return { line, col: index - lineStart + 1, lineText: text.slice(lineStart, lineEnd) };
}

function contextOk(text, start, end, context) {
  if (!context) return true;
  const from = Math.max(0, start - context.window);
  const to = Math.min(text.length, end + context.window);
  return compile(context.pattern, "i").test(text.slice(from, to));
}

function itemsOf(x) {
  if (Array.isArray(x)) return x;
  return (x && x.items) || [];
}

export function checkText(text, rules, opts = {}) {
  const norm = normalize(text);
  const out = [];
  itemsOf(rules).forEach((rule, order) => {
    const spans = [];
    for (const pattern of rule.patterns) {
      const re = compile(pattern, rule.flags);
      for (const m of norm.matchAll(re)) {
        if (m[0].length === 0) continue;
        spans.push([m.index, m.index + m[0].length]);
      }
    }
    spans.sort((a, b) => a[0] - b[0] || b[1] - a[1]);
    let lastEnd = -1;
    for (const [start, end] of spans) {
      if (start < lastEnd) continue;
      if (!contextOk(norm, start, end, rule.context)) continue;
      lastEnd = end;
      const { line, col, lineText } = lineInfo(norm, start);
      out.push({
        rule_id: rule.id,
        kind: rule.kind,
        severity: rule.severity,
        line,
        col,
        start,
        end,
        fragment: norm.slice(start, end),
        context: lineText.trim(),
        message: rule.message,
        act_id: rule.act_id ?? null,
        suggest_act_id: rule.suggest_act_id ?? null,
        quote_ids: rule.quote_ids || [],
        _order: order,
      });
    }
  });
  out.sort((a, b) => a.start - b.start || a._order - b._order);
  const acts = opts.acts ? new Map(itemsOf(opts.acts).map((a) => [a.id, a])) : null;
  return out.map(({ _order, ...f }) => {
    if (acts && f.suggest_act_id && !acts.has(f.suggest_act_id)) f.suggest_act_id = null;
    return f;
  });
}
