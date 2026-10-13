import argparse
import base64
import html
import sys
from pathlib import Path

from . import export
from .io import ROOT, today

QUESTIONS = {
    "quote": [("text", "Текст цитаты совпадает с вырезкой скана слово в слово?"),
              ("edition", "Это действующая редакция пункта на дату проверки?")],
    "rule": [("value", "Срок и единица (рабочие или календарные дни) указаны верно?"),
             ("start", "Отсчёт начинается с верного события?"),
             ("shift", "Перенос срока с выходного указан верно?"),
             ("who", "Кто должен уложиться в срок, указан верно?")],
    "act": [("status", "Статус акта на дату проверки указан верно?"),
            ("basis", "Основание статуса (цитата) подобрано верно?")],
    "indication": [("text", "Строка совпадает с текстом показаний в скане?"),
                   ("group", "Строка отнесена к верной группе заболеваний?")],
    "escalation": [("addressee", "Адресат ступени указан верно?"),
                   ("what", "Текст «что сделать» не противоречит норме?")],
}
CSS = """
body{font:15px/1.45 sans-serif;color:#222;max-width:46rem;margin:1.5rem auto;padding:0 1rem}
h1{font-size:1.4rem}h2{font-size:1.1rem;margin-top:1.5rem}
.draft{border:2px solid #222;padding:.5rem .75rem;font-weight:bold}
blockquote{border-left:4px solid #999;margin:0;padding:.25rem .75rem;white-space:pre-wrap}
img{max-width:100%;border:1px solid #999;margin:.5rem 0}
table{border-collapse:collapse;width:100%}td,th{border:1px solid #999;padding:.4rem;text-align:left;vertical-align:top}
.box{display:inline-block;width:1rem;height:1rem;border:1px solid #222;margin-right:.3rem;vertical-align:-.15rem}
pre{background:#f3f3f3;padding:.5rem;white-space:pre-wrap}
@media print{body{margin:0}}
"""


def find_target(envs: dict, target: str) -> tuple[str, dict]:
    for kind, name in export.TARGET_KINDS.items():
        for it in envs[name]["items"]:
            if it["id"] == target:
                return kind, it
    raise LookupError(f"нет акта, правила, ступени, цитаты или строки показаний {target}")


def crop_tags(root: Path, names: list[str]) -> str:
    out = []
    for n in names:
        p = root / "raw" / "crops" / n
        if p.is_file():
            data = base64.b64encode(p.read_bytes()).decode()
            out.append(f'<img alt="Вырезка скана {html.escape(n)}" src="data:image/png;base64,{data}">')
    return "\n".join(out)


def quote_block(root: Path, q: dict, acts: dict) -> str:
    a = acts.get(q["act_id"], {})
    crops = (q.get("scan_checked") or {}).get("crops") or []
    rows = [("Цитата", q["id"]), ("Пункт", q.get("point") or ""), ("Акт", f"{a.get('number', '')} {a.get('title', '')}"),
            ("eoNumber", a.get("eoNumber") or "нет на портале"), ("Публикация", a.get("url") or ""),
            ("Страница скана", str(q.get("page") or "")), ("Редакция", q.get("edition") or "")]
    table = "".join(f"<tr><th>{html.escape(k)}</th><td>{html.escape(v)}</td></tr>" for k, v in rows)
    return (f"<table>{table}</table>\n<blockquote>{html.escape(q['text'])}</blockquote>\n"
            + crop_tags(root, crops))


def render(root: Path, target: str) -> tuple[str, str]:
    envs = {e["dataset"]: e for e in export.datasets(root)}
    kind, item = find_target(envs, target)
    acts = {a["id"]: a for a in envs["acts"]["items"]}
    quotes = {q["id"]: q for q in envs["quotes"]["items"]}
    role = "medic" if kind == "indication" else "lawyer"
    parts = [f"<h1>Проверка: {html.escape(target)}</h1>",
             '<p class="draft">Черновик проекта openpalliative. Нужна проверка юристом (или медиком) в РФ. '
             "Отметьте ответ на каждый вопрос и верните лист мейнтейнеру</p>"]
    if kind == "quote":
        parts.append(quote_block(root, item, acts))
    elif kind == "indication":
        q = {"id": item["id"], "act_id": item["act_id"], "point": item["point"], "page": item.get("page"),
             "text": item["text"], "scan_checked": item.get("scan_checked")}
        parts.append(f"<p>Группа: {html.escape(item.get('group_title') or '')}</p>" + quote_block(root, q, acts))
    elif kind == "act":
        basis = (item.get("status_basis") or {}).get("quote_id")
        parts.append(f"<p>{html.escape(item['number'])} {html.escape(item['title'])}<br>Статус: {html.escape(item['status'])}"
                     f"<br>eoNumber: {html.escape(item.get('eoNumber') or 'нет на портале')}</p>")
        if basis and basis in quotes:
            parts.append(quote_block(root, quotes[basis], acts))
    else:
        desc = item.get("situation") or item.get("title") or ""
        what = (f"Срок: {item['value']} ({item['unit']}), отсчёт: {item.get('from_event_label', '')}, кто: {item.get('who', '')}"
                if kind == "rule" else f"Адресат: {item.get('addressee_kind', '')}. {item.get('what', '')}")
        parts.append(f"<p>{html.escape(desc)}<br>{html.escape(what)}</p>")
        for qid in item.get("quote_ids") or []:
            if qid in quotes:
                parts.append(quote_block(root, quotes[qid], acts))
    parts.append("<h2>Вопросы</h2><table><tr><th>Вопрос</th><th>Верно</th><th>Неверно</th><th>Не знаю</th></tr>")
    for _, text in QUESTIONS[kind]:
        parts.append(f"<tr><td>{html.escape(text)}</td>" + '<td><span class="box"></span></td>' * 3 + "</tr>")
    parts.append("</table><p>Комментарий:</p><p>____________________________________________</p>"
                 "<p>ФИО, роль (юрист или медик), дата: ____________________________</p>")
    template = "\n".join([f"target_kind: {kind}", f"target: {target}", f"role: {role}", f"reviewed_at: {today()}",
                          "expires_after: 1y", "verdict: ok  # ok, wrong или unsure", "questions:"]
                         + [f"  {qid}: yes  # yes, no или unsure" for qid, _ in QUESTIONS[kind]] + ["ref:", "notes:"])
    parts.append(f"<h2>Для мейнтейнера</h2><p>Перенесите ответы в файл и выполните "
                 f"<code>uv run python -m pipeline.review_ingest файл</code></p><pre>{html.escape(template)}</pre>")
    body = "\n".join(parts)
    page = (f'<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Проверка {html.escape(target)}</title>'
            f'<meta name="viewport" content="width=device-width, initial-scale=1"><style>{CSS}</style></head><body>{body}</body></html>\n')
    return page, template


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="pipeline.review_sheet")
    p.add_argument("target")
    p.add_argument("--out", type=Path)
    a = p.parse_args(argv)
    try:
        page, _ = render(ROOT, a.target)
    except LookupError as e:
        print(e, file=sys.stderr)
        return 1
    out = a.out or ROOT / "_reports" / "review" / f"{a.target}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
