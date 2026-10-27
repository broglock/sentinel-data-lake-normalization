# Solution kit: ASIM-style hunting on the Sentinel data lake

Working files for the design in the Claude Doc "ASIM-style hunting on the Sentinel data lake: questions and solution". Everything here runs without stored functions, so it works in lake KQL, KQL jobs and lake notebooks.

## Layout

| Path | What it is |
|---|---|
| `registry/groups.example.yaml` | Grammar-group registry: one entry per table and message format, with field rules, templates, result and record-key expressions. Four worked examples: Linux sshd syslog, Palo Alto CEF, a custom JSON table, a raw custom table. |
| `registry/vocab.yaml` | Result vocabulary, role tokens, synonyms, null values. |
| `generator/generate.py` | Turns the registry into KQL job queries and `notebook_config.json`. Approved groups (`status: approved`) are batched into one entity job and at most one event job per source table; everything else goes to the notebook. |
| `generator/asim_expand.py` | Makes an ASIM parser's KQL lake-safe: parameters to `let`, known helpers inlined, remaining function calls reported. |
| `notebooks/01_inventory_and_mining.py` | Daily and change-driven: reads only new tables, tables whose schema changed, and approved groups whose unmatched share went above 5%. Writes the field inventory with proposed ASIM names and roles, and mines templates from unmatched lines only. |
| `notebooks/02_index_longtail.py` | Hourly: indexes the groups not yet approved into `HuntEntity_SPRK` (hourly rollup plus `_stats` rows) and `HuntEvent_SPRK`. |
| `notebooks/03_coverage.py` | Daily: per-group tier, extraction rate, template match rate, unknown-role share and status, from the `_stats` rows; reads no source table. |
| `mcp/tools.yaml` | Seven MCP tools with their KQL and the agent instructions. hunt_value and hunt_entity sum `Count` over the rollup; auth_events and network_events read HuntEvent. |
| `examples/five-sources/` | Five log sources end to end (Windows SecurityEvent, FortiGate CEF, sshd Syslog, a JSON app table, a raw VPN table): registry, generated KQL, demo script and `output.md` with the actual index rows and hunt results. |
| `tests/run_all.sh` | Offline checks: generator, KQL parse and schema check (Microsoft Kusto.Language library), ASIM expander, notebooks with a fake provider (pyspark). |
| `tests/lab-test-plan.md` | Tests to run in a lab tenant for the open questions. |

## Order of work

1. Run `notebooks/01_inventory_and_mining.py` in the lake to get `FieldInventory_SPRK` and `TemplateCandidates_SPRK`.
2. Write registry entries for the grammar groups, starting with the highest volume. Use the proposals; review roles and results by hand. New entries start as `status: proposed` and are indexed by notebook 02.
3. When a group's coverage is good, set `status: approved`. Run `tests/run_all.sh`, then `generator/generate.py`.
4. Create KQL jobs from `out/kql_jobs/*.kql` (one entity job and at most one event job per source table; hourly, start minutes staggered, output appended to the lake tables). Create the notebook jobs for 02 (hourly) and 01, 03 (daily) with `notebook_config.json` pasted in. Notebook 02 skips approved groups, and notebook 01 only returns to them when their unmatched share rises.
5. Save the MCP tools and the agent instructions.
6. Check `HuntCoverage_SPRK` after a day; work the groups whose status is not `ok`.

## Status

Offline checks pass: generated KQL parses and resolves against stand-in schemas, and the notebook logic produces the expected rows on sample data. The design has since been deployed and run in a test tenant with the data lake onboarded. Record lab results and dates in `tests/lab-test-plan.md`; production-volume behaviour is still open (see `../notes/cost-model-1tb-day.md`).
