import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

import yaml

from .io import ROOT, dump_yaml, read_yaml
from .pravo import Client, SourceFormatError, SourceUnavailable, Transport, document_url, parse_meta

CANARY_EO = "0001202505290031"
CANARY_PAGES = 196
TOPIC_FORMS = ("паллиативной", "паллиативная", "паллиативную", "паллиативных")
BLOCKS = {"federal_law": "president", "code": "president", "government_decree": "government",
          "government_order": "government", "ministry_order": "federal_authorities",
          "joint_order": "federal_authorities"}
TRANSFER_QUERY = "О переносе выходных дней"
SUNSET_DAYS = 120
EXTERNAL_LIMIT = 300
TITLE_WORDS = 12
UNREACHABLE_AFTER = 3
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября",
          "ноября", "декабря"]
STATE_PATH = Path("data") / "snapshots" / "watch-state.json"


def request_key(path: str, params: dict | None) -> str:
    return path + "?" + urllib.parse.urlencode(sorted((params or {}).items()))


class FixtureTransport(Transport):
    def __init__(self, folder: Path, fail: bool = False):
        self.folder = Path(folder)
        self.index = json.loads((self.folder / "index.json").read_text(encoding="utf-8"))
        self.fail = fail
        self.calls: list[str] = []

    def get(self, path: str, params: dict | None = None) -> bytes:
        key = request_key(path, params)
        self.calls.append(key)
        if self.fail:
            raise SourceUnavailable(key + ": нет сети")
        name = self.index.get(key)
        if name:
            return (self.folder / name).read_bytes()
        if path == "/api/Documents":
            return json.dumps({"items": [], "itemsTotalCount": 0, "itemsPerPage": params.get("PageSize", 30),
                               "currentPage": 1, "pagesTotalCount": 0}).encode()
        raise SourceUnavailable(key + ": нет записанного ответа")


class RecordingTransport(Transport):
    def __init__(self, inner: Transport, folder: Path):
        self.inner = inner
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        idx = self.folder / "index.json"
        self.index = json.loads(idx.read_text(encoding="utf-8")) if idx.is_file() else {}

    def get(self, path: str, params: dict | None = None) -> bytes:
        body = self.inner.get(path, params)
        key = request_key(path, params)
        name = hashlib.sha256(key.encode()).hexdigest()[:16] + (".pdf" if path.startswith("/file/") else ".json")
        (self.folder / name).write_bytes(body)
        self.index[key] = name
        (self.folder / "index.json").write_text(json.dumps(self.index, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                                                encoding="utf-8")
        return body


def ru_date_words(iso: str) -> str:
    d = dt.date.fromisoformat(iso)
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def mentions_date(text: str, iso: str) -> bool:
    d = dt.date.fromisoformat(iso)
    text = re.sub(r"\s+", " ", text)
    return d.strftime("%d.%m.%Y") in text or ru_date_words(iso) in text


def search_number(number: str) -> str:
    return number.split("/")[0].strip()


def known_eos(acts: list[dict], years: list[dict]) -> set:
    eos = {a["eoNumber"] for a in acts if a.get("eoNumber")}
    eos |= {m["eoNumber"] for a in acts for m in a.get("amended_by") or []}
    eos |= {y["decree_eoNumber"] for y in years if y.get("decree_eoNumber")}
    return eos


def item_title(item: dict) -> str:
    return re.sub(r"\s+", " ", item.get("complexName") or item.get("name") or "").strip()


MD_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+!|<>~])")


def clean_external(text: str, limit: int = EXTERNAL_LIMIT) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    text = MD_SPECIAL.sub(r"\\\1", text)
    text = re.sub(r"(?i)\b(https?|ftp)://", r"\1[:]//", text)
    text = re.sub(r"(?i)\bwww\.", "www[.]", text)
    text = text.replace("@", "@ ")
    if len(text) > limit:
        text = text[: limit - 1].rstrip().rstrip("\\") + "…"
    return text


def load_territories(root: Path) -> list:
    path = root / "opsite" / "lint" / "territories.yaml"
    if not path.is_file():
        return []
    return [re.compile(p) for p in yaml.safe_load(path.read_text(encoding="utf-8"))["patterns"]]


class TerritoryFilter:
    def __init__(self, patterns: list):
        self.patterns = patterns
        self.skipped: list[str] = []

    def blocked(self, item: dict) -> bool:
        text = item_title(item)
        if any(p.search(text) for p in self.patterns):
            self.skipped.append(item.get("eoNumber") or "")
            return True
        return False


def review(kind: str, title: str, body: str, eo: str | None = None, source: str | None = None) -> dict:
    src = source or (document_url(eo) if eo else "")
    key = hashlib.sha256((kind + (eo or src)).encode()).hexdigest()[:8]
    return {"kind": kind, "title": title, "body": body, "source": src, "eoNumber": eo or "", "key": key}


def remember(state: dict, item: dict) -> dict | None:
    eo = item["eoNumber"]
    new = {"pagesCount": item.get("pagesCount"), "pdfFileLength": item.get("pdfFileLength"),
           "publishDateShort": (item.get("publishDateShort") or "")[:10]}
    old = state["seen"].get(eo)
    state["seen"][eo] = new
    if old and (old.get("pagesCount"), old.get("pdfFileLength")) != (new["pagesCount"], new["pdfFileLength"]):
        return old
    return None


def canary(client: Client) -> None:
    raw = client.document_raw(CANARY_EO)
    meta = parse_meta(raw)
    if meta.pages != CANARY_PAGES:
        raise SourceFormatError(f"у контрольного документа {meta.pages} страниц вместо {CANARY_PAGES}")
    if client.search(30, 1, Name="паллиативной").total <= 0:
        raise SourceFormatError("поиск по слову «паллиативной» ничего не вернул")


def watch_acts(client: Client, acts: list[dict], known: set, state: dict, out: list,
               terr: TerritoryFilter | None = None) -> None:
    terr = terr or TerritoryFilter([])
    by_eo = {a["eoNumber"]: a for a in acts if a.get("eoNumber")}
    for a in acts:
        if not a.get("eoNumber"):
            continue
        items = client.search_all(30, 3, Name=search_number(a["number"]), Block=BLOCKS[a["kind"]])
        for it in items:
            eo = it["eoNumber"]
            if eo == a["eoNumber"]:
                old = remember(state, it)
                if old:
                    out.append(review("republished", f"Документ переопубликован: {a['short_title']}",
                                      f"У публикации {eo} изменилось число страниц или размер PDF: было {old}, "
                                      f"стало {state['seen'][eo]}. Нужно сверить цитаты.", eo))
                continue
            if eo in known or eo in by_eo or eo in state["seen"]:
                continue
            title = item_title(it)
            if mentions_date(title, a["doc_date"]):
                remember(state, it)
                if terr.blocked(it):
                    continue
                out.append(review("amendment_or_repeal", f"Изменение или отмена: {a['short_title']}",
                                  f"Найден документ, который ссылается на {a['number']} от {a['doc_date']}: "
                                  f"{clean_external(title)}. Нужно прочитать текст и решить, меняет ли он статус "
                                  "или пункты.", eo))
        state["queries"][f"act:{a['id']}"] = {"total": len(items), "last_eo": items[0]["eoNumber"] if items else ""}


def title_query(title: str) -> str:
    words = re.sub(r"[«»\"()]", " ", title).split()
    return " ".join(words[:TITLE_WORDS])


def number_query(a: dict) -> str:
    d = dt.date.fromisoformat(a["doc_date"])
    return f"от {d.strftime('%d.%m.%Y')} № {a['number']}"


def norm_words(text: str) -> str:
    return " ".join(re.sub(r"[^0-9a-zа-яё]+", " ", text.lower().replace("ё", "е")).split())


def refers_to(a: dict, title: str) -> bool:
    t = norm_words(title)
    if norm_words(title_query(a["title"])) in t:
        return True
    return mentions_date(title, a["doc_date"]) and norm_words(a["number"]) in t


def watch_acts_without_eo(client: Client, acts: list[dict], known: set, state: dict, out: list,
                          terr: TerritoryFilter, baseline: list) -> None:
    for a in acts:
        if a.get("eoNumber") or a.get("status") == "repealed" or not a.get("doc_date") or not a.get("number"):
            continue
        key = f"noeo:{a['id']}"
        first = key not in state["queries"]
        items: dict = {}
        for q in (title_query(a["title"]), number_query(a)):
            for it in client.search_all(30, 3, Name=q, Block=BLOCKS[a["kind"]]):
                items.setdefault(it["eoNumber"], it)
        ordered = sorted(items.values(), key=lambda it: it.get("publishDateShort") or "", reverse=True)
        for it in ordered:
            eo = it["eoNumber"]
            if eo in known or eo in state["seen"] or not refers_to(a, item_title(it)):
                continue
            remember(state, it)
            if terr.blocked(it):
                continue
            if first:
                baseline.append({"act_id": a["id"], "eoNumber": eo, "title": clean_external(item_title(it))})
                continue
            out.append(review("amendment_or_repeal", f"Изменение или отмена: {a['short_title']}",
                              f"Найден документ, в названии которого упомянут {a['number']} от {a['doc_date']} "
                              f"или его название: {clean_external(item_title(it))}. Номера публикации у самого "
                              "документа на портале нет. Нужно прочитать текст и решить, что он меняет.", eo))
        state["queries"][key] = {"total": len(ordered), "last_eo": ordered[0]["eoNumber"] if ordered else ""}


def watch_topic(client: Client, known: set, state: dict, cutoff: str, out: list,
                terr: TerritoryFilter | None = None) -> None:
    terr = terr or TerritoryFilter([])
    for block in ("president", "government", "federal_authorities"):
        for form in TOPIC_FORMS:
            items, index = [], 1
            while index <= 5:
                page = client.search(30, index, Name=form, Block=block)
                items += page.items
                if not page.items or (page.items[-1].get("publishDateShort") or "")[:10] < cutoff \
                        or index >= page.pages_total:
                    break
                index += 1
            fresh = [it for it in items if (it.get("publishDateShort") or "")[:10] >= cutoff]
            for it in fresh:
                eo = it["eoNumber"]
                if eo in known or eo in state["seen"]:
                    continue
                remember(state, it)
                if terr.blocked(it):
                    continue
                out.append(review("new_act", f"Новый документ о паллиативной помощи: {clean_external(item_title(it), 120)}",
                                  f"{clean_external(item_title(it))}. Опубликован "
                                  f"{(it.get('publishDateShort') or '')[:10]}. Нужно решить, добавлять ли его в acts.yaml.",
                                  eo))
            state["queries"][f"topic:{block}:{form}"] = {"total": len(items),
                                                         "last_eo": items[0]["eoNumber"] if items else ""}


TRANSFER_LINE = re.compile(r"с\s+(?:субботы|воскресенья)\s+(\d{1,2})\s+([а-я]+)\s+на\s+[а-я]+\s+(\d{1,2})\s+([а-я]+)")


def parse_transfers(text: str, year: int) -> list[dict]:
    out = []
    for m in TRANSFER_LINE.finditer(re.sub(r"\s+", " ", text.lower())):
        d1, m1, d2, m2 = m.groups()
        if m1 not in MONTHS or m2 not in MONTHS:
            continue
        out.append({"from": dt.date(year, MONTHS.index(m1) + 1, int(d1)).isoformat(),
                    "to": dt.date(year, MONTHS.index(m2) + 1, int(d2)).isoformat()})
    return out


def watch_transfers(client: Client, known: set, state: dict, out: list, max_year: int,
                    terr: TerritoryFilter | None = None) -> list[dict]:
    terr = terr or TerritoryFilter([])
    items = client.search_all(30, 1, Name=TRANSFER_QUERY, Block="government")
    new = []
    for it in items:
        eo = it["eoNumber"]
        if eo in known or eo in state["seen"]:
            continue
        m = re.search(r"в (\d{4}) году", it.get("name") or item_title(it))
        if not m or int(m.group(1)) <= max_year:
            continue
        remember(state, it)
        if terr.blocked(it):
            continue
        new.append({"eoNumber": eo, "year": int(m.group(1)), "item": it})
        out.append(review("transfer_decree", f"Постановление о переносе выходных дней в {m.group(1)} году",
                          f"{clean_external(item_title(it))}. Наблюдатель подготовил черновик календаря, его нужно "
                          "сверить со сканом.", eo))
    state["queries"]["transfers"] = {"total": len(items), "last_eo": items[0]["eoNumber"] if items else ""}
    return new


def watch_sunset(acts: list[dict], today: dt.date, out: list) -> None:
    for a in acts:
        if a.get("valid_until") and a.get("status") == "in_force":
            left = (dt.date.fromisoformat(a["valid_until"]) - today).days
            if 0 <= left <= SUNSET_DAYS:
                out.append(review("sunset_soon", f"Скоро истекает срок действия: {a['short_title']}",
                                  f"Документ действует до {a['valid_until']}, осталось {left} дн. "
                                  "Нужно найти новый документ или продление.", a.get("eoNumber")))


def empty_state() -> dict:
    return {"checked_at": "", "last_ok_at": "", "consecutive_failures": 0, "seen": {}, "queries": {}}


def load_state(root: Path) -> dict:
    path = root / STATE_PATH
    state = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else empty_state()
    for k, v in empty_state().items():
        state.setdefault(k, v)
    return state


def run(client: Client, root: Path = ROOT, now: dt.datetime | None = None) -> tuple[dict, dict, list]:
    now = now or dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    stamp = now.isoformat().replace("+00:00", "Z")
    acts = read_yaml(root / "data" / "acts.yaml")["acts"]
    years = read_yaml(root / "data" / "calendar" / "transfers.yaml")["years"]
    prev = load_state(root)
    state = json.loads(json.dumps(prev))
    state["checked_at"] = stamp
    report = {"checked_at": stamp, "ok": False, "facts": [], "review": [], "drafts": [], "baseline": [],
              "skipped_territory": 0}
    terr = TerritoryFilter(load_territories(root))
    try:
        canary(client)
        known = known_eos(acts, years)
        last = prev["last_ok_at"][:10] if prev["last_ok_at"] else (now.date() - dt.timedelta(days=60)).isoformat()
        cutoff = (dt.date.fromisoformat(last) - dt.timedelta(days=14)).isoformat()
        watch_acts(client, acts, known, state, report["review"], terr)
        watch_acts_without_eo(client, acts, known, state, report["review"], terr, report["baseline"])
        watch_topic(client, known, state, cutoff, report["review"], terr)
        max_year = max([int(y["year"]) for y in years] or [now.year])
        decrees = watch_transfers(client, known, state, report["review"], max_year, terr)
        watch_sunset(acts, now.date(), report["review"])
        report["skipped_territory"] = len(terr.skipped)
    except SourceFormatError as e:
        report["review"] = [review("source_format", "Изменился формат ответа pravo.gov.ru", str(e),
                                   source="http://publication.pravo.gov.ru/api/Documents")]
        prev["checked_at"] = stamp
        return report, prev, []
    except SourceUnavailable as e:
        prev["checked_at"] = stamp
        prev["consecutive_failures"] = int(prev.get("consecutive_failures") or 0) + 1
        report["error"] = str(e)
        if prev["consecutive_failures"] >= UNREACHABLE_AFTER:
            report["review"] = [review("unreachable", "Наблюдатель не достучался до pravo.gov.ru",
                                       f"Неудачных проверок подряд: {prev['consecutive_failures']}. Последняя ошибка: {e}",
                                       source="http://publication.pravo.gov.ru/")]
        report["facts"].append({"path": STATE_PATH.as_posix(), "what": "неудачная проверка", "source": ""})
        return report, prev, []
    state["last_ok_at"] = stamp
    state["consecutive_failures"] = 0
    report["ok"] = True
    report["facts"].append({"path": STATE_PATH.as_posix(), "what": f"снимок pravo.gov.ru, известных публикаций "
                            f"{len(state['seen'])}", "source": "http://publication.pravo.gov.ru/api/Documents"})
    return report, state, decrees


def write_state(root: Path, state: dict) -> None:
    path = root / STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    state["seen"] = dict(sorted(state["seen"].items()))
    state["queries"] = dict(sorted(state["queries"].items()))
    path.write_text(json.dumps(state, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def draft_decree(client: Client, root: Path, decree: dict, today: str, ocr_text=None) -> list[str]:
    eo, year, item = decree["eoNumber"], decree["year"], decree["item"]
    if ocr_text is None:
        from . import fetch_pravo, ocr
        fetch_pravo.save_meta(client, eo, root)
        fetch_pravo.save_pdf(client, eo, root)
        text = ocr.ocr_page(eo, 1, "a", root)
    else:
        text = ocr_text
    transfers = parse_transfers(text, year)
    tpath = root / "data" / "calendar" / "transfers.yaml"
    data = read_yaml(tpath)
    if any(str(y["year"]) == str(year) for y in data["years"]):
        return []
    data["years"].append({"year": year, "decree_act_id": "", "decree_eoNumber": eo, "source_ref": f"pravo-{eo}",
                          "verified": False, "verified_at": "", "quote_ids": [], "transfers": transfers})
    dump_yaml(data, tpath)
    cpath = root / "data" / "changes.yaml"
    changes = read_yaml(cpath)
    published = (item.get("publishDateShort") or "")[:10]
    changes["changes"].insert(0, {
        "id": f"{published}-transfer-decree-{eo}", "verified": False, "verified_at": "", "source_ref": f"pravo-{eo}",
        "published_at": published, "detected_at": today, "eoNumber": eo, "title": item_title(item),
        "kind": "transfer_decree", "related_act_ids": [], "summary": f"Опубликовано постановление о переносе выходных дней в {year} году",
        "state": "accepted", "review_ref": ""})
    dump_yaml(changes, cpath)
    return [tpath.relative_to(root).as_posix(), cpath.relative_to(root).as_posix()]


def issue_title(item: dict) -> str:
    return f"[watch:{item['key']}] {item['title']}"


def open_issues(report: dict, runner=subprocess.run) -> list[str]:
    created = []
    for item in report.get("review", []):
        if item["kind"] == "transfer_decree":
            continue
        tag = f"[watch:{item['key']}]"
        res = runner(["gh", "issue", "list", "--state", "all", "--search", f"{tag} in:title", "--json", "title",
                      "--limit", "20"], capture_output=True, text=True, check=True)
        if any(tag in x.get("title", "") for x in json.loads(res.stdout or "[]")):
            continue
        body = f"{item['body']}\n\nИсточник: <{item['source']}>\n\nНаблюдатель pal-norms, {report['checked_at']}"
        cmd = ["gh", "issue", "create", "--title", issue_title(item), "--body", body]
        try:
            runner(cmd + ["--label", "review:data"], capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError:
            runner(cmd, capture_output=True, text=True, check=True)
        created.append(issue_title(item))
    return created


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="pipeline.watch")
    p.add_argument("--fixtures", type=Path)
    p.add_argument("--record", type=Path)
    p.add_argument("--report", type=Path, default=Path("_reports/watch.json"))
    p.add_argument("--apply", action="store_true")
    p.add_argument("--open-issues", type=Path)
    a = p.parse_args(argv)
    if a.open_issues:
        created = open_issues(json.loads(a.open_issues.read_text(encoding="utf-8")))
        print(f"Новых задач: {len(created)}")
        return 0
    transport = FixtureTransport(a.fixtures) if a.fixtures else None
    client = Client(transport) if transport else Client()
    if a.record:
        client = Client(RecordingTransport(client.t, a.record))
    report, state, decrees = run(client)
    if a.apply:
        write_state(ROOT, state)
        for d in decrees:
            report["drafts"] += draft_decree(client, ROOT, d, report["checked_at"][:10])
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Проверка {'прошла' if report['ok'] else 'не прошла'}: на ревью {len(report['review'])}, "
          f"черновиков {len(report['drafts'])}")
    return 0 if report["ok"] or a.fixtures is None else 1


if __name__ == "__main__":
    sys.exit(main())
