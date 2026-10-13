import json
import sqlite3
import sys
from pathlib import Path

META_KEYS = ("dataset", "repo", "schema_version", "version", "generated_at", "data_date", "stale_after_days",
             "license", "content_sha256")


def cell(value):
    if isinstance(value, bool):
        return int(value)
    if value is None or isinstance(value, (str, int, float)):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def table_name(dataset: str) -> str:
    return dataset.replace("-", "_")


def build(src: Path, out: Path) -> dict:
    index = json.loads((src / "index.json").read_text(encoding="utf-8"))
    if out.exists():
        out.unlink()
    db = sqlite3.connect(out)
    db.execute(f"CREATE TABLE datasets ({', '.join(META_KEYS)}, items INTEGER, file TEXT, file_sha256 TEXT)")
    db.execute("CREATE TABLE sources (dataset TEXT, position INTEGER, source TEXT)")
    counts = {}
    for entry in index["datasets"]:
        env = json.loads((src / entry["path"]).read_text(encoding="utf-8"))
        items = env["items"]
        columns = sorted({k for it in items for k in it})
        if "id" in columns:
            columns.remove("id")
            columns.insert(0, "id")
        name = table_name(env["dataset"])
        cols = ", ".join(f'"{c}"' + (" TEXT PRIMARY KEY" if c == "id" else "") for c in columns)
        db.execute(f'CREATE TABLE "{name}" ({cols})')
        marks = ", ".join("?" for _ in columns)
        db.executemany(f'INSERT INTO "{name}" VALUES ({marks})',
                       [[cell(it.get(c)) for c in columns] for it in items])
        db.execute(f"INSERT INTO datasets VALUES ({', '.join('?' for _ in META_KEYS)}, ?, ?, ?)",
                   [cell(env.get(k)) for k in META_KEYS] + [len(items), entry["path"], entry["sha256"]])
        db.executemany("INSERT INTO sources VALUES (?, ?, ?)",
                       [(env["dataset"], i, cell(s)) for i, s in enumerate(env.get("source") or [])])
        if len(items) != entry["items"]:
            raise SystemExit(f"{entry['path']}: в index.json {entry['items']} записей, в файле {len(items)}")
        counts[env["dataset"]] = len(items)
    db.commit()
    db.execute("VACUUM")
    db.close()
    return counts


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Использование: datasets_sqlite.py <папка data/v1> <файл .sqlite>")
        return 2
    counts = build(Path(argv[0]), Path(argv[1]))
    print(f"{argv[1]}: наборов {len(counts)}, записей {sum(counts.values())}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
