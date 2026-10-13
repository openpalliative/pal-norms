import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

BASE = "http://publication.pravo.gov.ru"
USER_AGENT = "openpalliative-watch (+https://github.com/openpalliative)"
PAGE_SIZES = (10, 30, 100, 200)
BLOCKS = ("president", "government", "federal_authorities")
RETRY_PAUSES = (2, 4, 8, 16)
META_KEYS = ("eoNumber", "number", "documentDate", "pagesCount", "name")
DENY_BLOCKS = frozenset({"region80", "region81", "region84", "region85", "region91", "region92"})
DENY_EO_PREFIXES = tuple(b[-2:] for b in sorted(DENY_BLOCKS))


def guard_eo(eo: str) -> None:
    if str(eo).startswith(DENY_EO_PREFIXES):
        raise ValueError("публикации этого блока не запрашиваем")


class SourceFormatError(Exception):
    pass


class SourceUnavailable(Exception):
    pass


@dataclass
class DocMeta:
    eoNumber: str
    number: str
    document_date: str
    publish_date: str
    name: str
    complex_name: str
    pages: int | None
    pdf_bytes: int | None
    authority_ids: list[str] = field(default_factory=list)
    authorities: list[str] = field(default_factory=list)
    document_type: str | None = None

    @property
    def url(self) -> str:
        return document_url(self.eoNumber)

    @property
    def pdf_url(self) -> str:
        return pdf_url(self.eoNumber)


def document_url(eo: str) -> str:
    return f"{BASE}/document/{eo}"


def pdf_url(eo: str) -> str:
    return f"{BASE}/file/pdf?eoNumber={eo}"


def parse_meta(raw: dict) -> DocMeta:
    if not isinstance(raw, dict) or any(k not in raw for k in META_KEYS):
        raise SourceFormatError("в ответе нет полей " + ", ".join(k for k in META_KEYS if not isinstance(raw, dict) or k not in raw))
    auths = raw.get("signatoryAuthorities") or []
    ids = [a.get("id") for a in auths if a.get("id")]
    if not ids and raw.get("signatoryAuthorityId"):
        ids = [raw["signatoryAuthorityId"]]
    main_first = sorted(auths, key=lambda a: not a.get("isMain"))
    return DocMeta(
        eoNumber=str(raw["eoNumber"]),
        number=str(raw["number"] or ""),
        document_date=str(raw["documentDate"] or "")[:10],
        publish_date=str(raw.get("publishDateShort") or "")[:10],
        name=(raw.get("name") or "").strip(),
        complex_name=(raw.get("complexName") or "").strip(),
        pages=raw.get("pagesCount"),
        pdf_bytes=raw.get("pdfFileLength"),
        authority_ids=ids,
        authorities=[a.get("name", "") for a in main_first],
        document_type=(raw.get("documentType") or {}).get("name"),
    )


@dataclass
class Page:
    items: list[dict]
    total: int
    page: int
    pages_total: int


def parse_page(raw: dict) -> Page:
    if not isinstance(raw, dict) or "items" not in raw or "itemsTotalCount" not in raw:
        raise SourceFormatError("в ответе поиска нет items или itemsTotalCount")
    if not isinstance(raw["items"], list):
        raise SourceFormatError("items в ответе поиска не список")
    return Page(raw["items"], int(raw["itemsTotalCount"]), int(raw.get("currentPage") or 1),
                int(raw.get("pagesTotalCount") or 0))


class Transport:
    def get(self, path: str, params: dict | None = None) -> bytes:
        raise NotImplementedError


class HttpTransport(Transport):
    def __init__(self, pause: float = 2.0, timeout: float = 30.0, retries=RETRY_PAUSES, sleep=time.sleep):
        self.pause = pause
        self.timeout = timeout
        self.retries = retries
        self.sleep = sleep
        self._last = 0.0

    def get(self, path: str, params: dict | None = None) -> bytes:
        url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
        last_error = None
        for wait in (0, *self.retries):
            if wait:
                self.sleep(wait)
            gap = self.pause - (time.monotonic() - self._last)
            if gap > 0:
                self.sleep(gap)
            try:
                req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    body = r.read()
                self._last = time.monotonic()
                if body:
                    return body
                last_error = "пустой ответ"
            except OSError as e:
                self._last = time.monotonic()
                last_error = str(e)
        raise SourceUnavailable(f"{url}: {last_error}")


class Client:
    def __init__(self, transport: Transport | None = None):
        self.t = transport or HttpTransport()

    def _json(self, path: str, params: dict | None = None):
        body = self.t.get(path, params)
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise SourceFormatError(f"{path}: ответ не JSON") from e

    def document_raw(self, eo: str) -> dict:
        guard_eo(eo)
        return self._json("/api/Document", {"eoNumber": eo})

    def document(self, eo: str) -> DocMeta:
        return parse_meta(self.document_raw(eo))

    def search(self, page_size: int = 30, index: int = 1, **query) -> Page:
        if page_size not in PAGE_SIZES:
            raise ValueError(f"PageSize только {PAGE_SIZES}")
        if query.get("Block") in DENY_BLOCKS or query.get("Block") == "subjects":
            raise ValueError("этот блок не опрашиваем")
        params = {"PageSize": page_size, "Index": index}
        params.update({k: v for k, v in query.items() if v not in (None, "")})
        return parse_page(self._json("/api/Documents", params))

    def search_all(self, page_size: int = 30, limit_pages: int = 10, **query) -> list[dict]:
        out: list[dict] = []
        index = 1
        while index <= limit_pages:
            page = self.search(page_size=page_size, index=index, **query)
            out.extend(page.items)
            if index >= page.pages_total or not page.items:
                break
            index += 1
        return out

    def pdf(self, eo: str) -> bytes:
        guard_eo(eo)
        body = self.t.get("/file/pdf", {"eoNumber": eo})
        if not body.startswith((b"%PDF", b"PK\x03\x04")):
            raise SourceFormatError(f"{eo}: ответ не PDF и не архив сканов")
        return body
