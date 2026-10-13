import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def envs():
    from pipeline import export
    return {e["dataset"]: e for e in export.datasets(ROOT)}


@pytest.fixture
def tmp_root(tmp_path):
    for part in ("data", "raw/crops", "raw/ocr-diff", "raw/meta", "opsite/lint", "tests/fixtures"):
        src = ROOT / part
        if src.is_dir():
            shutil.copytree(src, tmp_path / part)
    return tmp_path


@pytest.fixture
def json_files(tmp_path, envs):
    out = {}
    for name in ("lint-rules", "acts"):
        p = tmp_path / f"{name}.json"
        p.write_text(json.dumps(envs[name], ensure_ascii=False), encoding="utf-8")
        out[name] = p
    return out
