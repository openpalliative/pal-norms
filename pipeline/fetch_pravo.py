import argparse
import io
import json
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from .io import ROOT, read_yaml, sha256_bytes, today
from .pravo import Client, SourceFormatError, SourceUnavailable, parse_meta, pdf_url


def save_meta(client: Client, eo: str, root: Path = ROOT) -> dict:
    raw = client.document_raw(eo)
    client_meta = parse_meta(raw)
    out = root / "raw" / "meta" / f"{eo}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    keep = {k: raw.get(k) for k in ("eoNumber", "number", "documentDate", "publishDateShort", "name",
                                     "complexName", "pagesCount", "pdfFileLength", "signatoryAuthorities",
                                     "signatoryAuthorityId", "documentType", "jdRegNumber", "jdRegDate")}
    out.write_text(json.dumps(keep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return {"meta": client_meta, "raw": keep}


def record_source(root: Path, eo: str, url: str, body: bytes) -> str:
    tsv = root / "raw" / "SOURCES.tsv"
    rows = tsv.read_text(encoding="utf-8").splitlines() if tsv.is_file() else ["eoNumber\turl\tsha256\tbytes\tretrieved_at"]
    sha = sha256_bytes(body)
    rows = [r for r in rows if not r.startswith(eo + "\t")]
    rows.append(f"{eo}\t{url}\t{sha}\t{len(body)}\t{today()}")
    tsv.write_text("\n".join([rows[0], *sorted(rows[1:])]) + "\n", encoding="utf-8")
    return sha


def tiffs_to_pdf(archive: bytes, out: Path) -> None:
    with zipfile.ZipFile(io.BytesIO(archive)) as z, tempfile.TemporaryDirectory() as tmp:
        names = sorted(n for n in z.namelist() if re.fullmatch(r"\d{1,5}\.tiff?", n, re.I))
        if not names:
            raise SourceFormatError("в архиве нет страниц TIFF")
        parts = []
        for n in names:
            tif = Path(tmp) / Path(n).name
            tif.write_bytes(z.read(n))
            pdf = tif.with_suffix(".pdf")
            subprocess.run(["tiff2pdf", "-o", str(pdf), str(tif)], check=True, capture_output=True)
            parts.append(str(pdf))
        subprocess.run(["pdfunite", *parts, str(out)], check=True, capture_output=True)


def save_pdf(client: Client, eo: str, root: Path = ROOT) -> Path:
    path = root / "raw" / "cache" / f"{eo}.pdf"
    archive = path.with_suffix(".zip")
    if not path.is_file():
        body = client.pdf(eo)
        path.parent.mkdir(parents=True, exist_ok=True)
        if body.startswith(b"PK"):
            archive.write_bytes(body)
            tiffs_to_pdf(body, path)
        else:
            path.write_bytes(body)
    source = archive if archive.is_file() else path
    record_source(root, eo, pdf_url(eo), source.read_bytes())
    return path


def act_eos(root: Path, act_id: str | None) -> list[str]:
    acts = read_yaml(root / "data" / "acts.yaml")["acts"]
    eos = []
    for a in acts:
        if act_id and a["id"] != act_id:
            continue
        if a.get("eoNumber"):
            eos.append(a["eoNumber"])
        eos += [m["eoNumber"] for m in a.get("amended_by") or []]
    return eos


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="pipeline.fetch_pravo")
    p.add_argument("act_id", nargs="?")
    p.add_argument("--all", action="store_true")
    p.add_argument("--eo", nargs="*", default=[])
    p.add_argument("--pdf", action="store_true")
    a = p.parse_args(argv)
    eos = list(a.eo)
    if a.all or a.act_id:
        eos += act_eos(ROOT, None if a.all else a.act_id)
    client = Client()
    failed = 0
    for eo in dict.fromkeys(eos):
        try:
            m = save_meta(client, eo)["meta"]
            line = f"{eo}\t{m.number}\t{m.document_date}\t{m.pages}\t{m.name[:70]}"
            if a.pdf:
                save_pdf(client, eo)
                line += "\tpdf"
            print(line)
        except (SourceFormatError, SourceUnavailable) as e:
            failed += 1
            print(f"{eo}\tошибка: {e}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
