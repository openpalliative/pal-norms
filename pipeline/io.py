import datetime as dt
import hashlib
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def read_yaml(path: Path):
    with open(path, encoding="utf-8") as f:
        return yaml.load(f, Loader=getattr(yaml, "CBaseLoader", yaml.BaseLoader))


def _plain(obj):
    if obj is None:
        return ""
    if isinstance(obj, bool):
        return "true" if obj else "false"
    if isinstance(obj, (int, float)):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    return obj


class _Dumper(yaml.SafeDumper):
    def resolve(self, kind, value, implicit):
        if kind is yaml.ScalarNode:
            return "tag:yaml.org,2002:str"
        return super().resolve(kind, value, implicit)


def _str(dumper, data):
    style = "|" if "\n" in data else ("'" if re.fullmatch(r"0\d+|\d{13,}", data) else None)
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_Dumper.add_representer(str, _str)


def dump_yaml(obj, path: Path | None = None) -> str:
    text = yaml.dump(_plain(obj), Dumper=_Dumper, allow_unicode=True, sort_keys=False, width=10_000)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return text


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def today() -> str:
    return dt.date.today().isoformat()
