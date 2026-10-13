#!/bin/sh
set -eu
mkdir -p _reports
STEP=""
fail() { printf '{"ok": false, "step": "%s"}\n' "$STEP" > _reports/gate.json; echo "Ворота не пройдены на шаге: $STEP"; exit 1; }
run() { STEP="$1"; shift; echo "== $STEP"; "$@" || fail; }
run "uv sync" uv sync --frozen
run "pnpm install" pnpm install --frozen-lockfile
run "pytest" uv run pytest -q
run "data" uv run python -m pipeline.check
run "watch" uv run python -m pipeline.watch --fixtures pipeline/tests/fixtures/pravo --report _reports/watch.json
run "build fixtures" env PN_FIXTURES=1 uv run python -m opsite build
run "check fixtures" uv run python -m opsite check
run "build" uv run python -m opsite build
run "check" uv run python -m opsite check
run "unit" pnpm test:unit
run "e2e" pnpm test:e2e
run "shots" pnpm shots
printf '{"ok": true}\n' > _reports/gate.json
echo "Ворота пройдены"
