import json
import subprocess
import sys

from pipeline.tests.conftest import ROOT

sys.path.insert(0, str(ROOT / "tools"))
import pack_lint  # noqa: E402

GOLDEN = ROOT / "tests" / "golden" / "lint"


def test_golden_corpus(envs):
    for txt in sorted(GOLDEN.glob("*.txt")):
        expected = json.loads(txt.with_suffix(".expected.json").read_text(encoding="utf-8"))
        assert pack_lint.check_text(txt.read_text(encoding="utf-8"), envs["lint-rules"], envs["acts"]) == expected, txt.name


def run(json_files, *paths):
    return subprocess.run([sys.executable, str(ROOT / "tools" / "pack_lint.py"), *map(str, paths), "--rules",
                           str(json_files["lint-rules"]), "--acts", str(json_files["acts"]), "--json"],
                          capture_output=True, text=True)


def test_cli_exit_codes(json_files):
    bad = run(json_files, GOLDEN / "memo.txt")
    assert bad.returncode == 1
    assert len(json.loads(bad.stdout)) == 11
    ok = run(json_files, GOLDEN / "memo-ok.txt", GOLDEN / "other-act.txt")
    assert ok.returncode == 0 and json.loads(ok.stdout) == []


def test_norm_references(json_files, tmp_path):
    (tmp_path / "pack").mkdir()
    doc = tmp_path / "pack" / "doc.md"
    doc.write_text("Основание: {{ norm('208n-243n') }}, {{ norm('345n-372n') }}, {{ norm('59-fz') }}, {{ norm('nope') }}",
                   encoding="utf-8")
    res = run(json_files, tmp_path / "pack")
    found = json.loads(res.stdout)
    assert res.returncode == 1
    assert [f["act_id"] for f in found] == ["345n-372n", "59-fz", "nope"]


def test_only_stdlib():
    text = (ROOT / "tools" / "pack_lint.py").read_text(encoding="utf-8")
    imports = {line.split()[1].split(".")[0] for line in text.splitlines() if line.startswith(("import ", "from "))}
    assert imports <= {"argparse", "json", "re", "sys", "unicodedata", "pathlib"}
