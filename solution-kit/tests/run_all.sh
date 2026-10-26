#!/usr/bin/env bash
# Runs every offline check in the kit. Needs Python 3 with pyyaml, Node.js, and for the
# notebook test pyspark + Java. From the solution-kit folder:  bash tests/run_all.sh
set -euo pipefail
KIT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$(mktemp -d)"
cd "$KIT/tests"
[ -d node_modules/@kusto/language-service-next ] || npm install --silent @kusto/language-service-next

echo "== generate"
python3 "$KIT/generator/generate.py" --registry "$KIT/registry/groups.example.yaml" \
  --vocab "$KIT/registry/vocab.yaml" --out "$OUT"

echo "== KQL job queries (parse + schema check)"
node kql_check.js "$OUT"/kql_jobs/*.kql

echo "== MCP tool queries"
mkdir -p "$OUT/mcp"
python3 - "$KIT/mcp/tools.yaml" "$OUT/mcp" <<'PY'
import sys, yaml
for t in yaml.safe_load(open(sys.argv[1]))["tools"]:
    q = t["query"].replace("{SourceTable}", "Syslog").replace("{Table}", "Syslog") \
                  .replace("{EventStartTime}", "2026-10-18T09:20:00Z")
    open(f"{sys.argv[2]}/{t['name']}.kql", "w").write(q)
PY
node kql_check.js "$OUT"/mcp/*.kql

echo "== ASIM expander on the fixture"
python3 "$KIT/generator/asim_expand.py" fixtures/sample_parser.yaml --out "$OUT/expanded.kql"
node kql_check.js "$OUT/expanded.kql"

echo "== notebooks with a fake provider (pyspark)"
python3 test_notebook_local.py

echo "== five-source example: generate, check KQL, run end to end"
python3 "$KIT/examples/five-sources/run_demo.py" > "$OUT/five.log"
node kql_check.js "$KIT"/examples/five-sources/kql_out/kql_jobs/*.kql "$KIT"/examples/five-sources/kql_out_reviewed/kql_jobs/*.kql
tail -12 "$KIT/examples/five-sources/output.md"
