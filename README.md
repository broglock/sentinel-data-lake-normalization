# Sentinel Data Lake Normalization

How to get common, ASIM-style fields across hundreds of third-party log sources when hunting in the Microsoft Sentinel data lake, and what works at scale. The project has five parts:

- Ten infographics that explain the problem and the approach
- A blog post, "Hunting across hundreds of log sources in the Sentinel data lake"
- A design note with the full solution and the open questions
- A solution kit: registry, KQL generator, lake notebooks and MCP tool definitions, with a five-source worked example
- LevelBlue Lake Hunt, a containerised app (web UI, REST API and MCP server) built on the solution kit
- A static walkthrough demo of daily operations: `demo/index.html`, open it in a browser, no server needed

Audiences: customers and pre-sales, blog and LinkedIn, Microsoft product group feedback. Style: LevelBlue corporate palette and type. Facts checked 16 October 2026 (see `notes/research-notes.md`).

## Status

- Infographics: done, 17 October 2026.
- Blog post: draft, 18 October 2026, about 1,600 words with four images; HuntEntity described as an hourly rollup, cost at 1 TB/day quoted.
- Solution kit: offline checks pass (generated KQL parses against stand-in schemas, notebooks run on sample data). Nothing has run in a real lake yet. `solution-kit/tests/lab-test-plan.md` lists what to confirm first.
- Design: deployed and run in a test tenant with the Sentinel data lake onboarded. Production-volume behaviour (notebook run times, job limits at 1 TB/day) is not yet confirmed.
- Lake Hunt: version 1.0.0. The task-focused UI, recorded demo and new screenshots were added on 24 October 2026. The packaged zip from 18 October is not in this repository.

## Folders and files

| Path | What it is |
|---|---|
| `blog/hunting-across-hundreds-of-log-sources.md` | Blog post: why ASIM does not carry over to the lake, normalizing once into an index (HuntEntity and HuntEvent), the four mapping methods, onboarding a source, limits |
| `blog/hunting-across-hundreds-of-log-sources.html` | The same post as a styled LevelBlue page, one self-contained file with the images embedded |
| `blog/build/` | `build.py` and `style.css`: from inside `blog/build/`, run `python build.py ../hunting-across-hundreds-of-log-sources.md ../hunting-across-hundreds-of-log-sources.html` to regenerate the HTML after editing the Markdown (needs pandoc) |
| `blog/img/` | The four blog images: `01-before-after`, `02-mapping-layers`, `03-architecture`, `04-onboarding` |
| `notes/asim-lake-hunting-solution.md` | Design note, 18 October 2026: questions to ask, platform facts, the two lake tables, mapping layers and precedence, role and result rules, job budget, data lake MCP integration, coverage and drift, onboarding, lab tests and sources |
| `notes/cost-model-1tb-day.md` | Planning cost model at 1 TB/day: index build, index size and storage, hunt cost, hourly entity rollup, controls and lab tests (26 October 2026) |
| `notes/research-notes.md` | Facts, sources and items still to verify in a lab |
| `diagrams/architecture.png`, `diagrams/onboarding.png` | Architecture and onboarding diagrams used in the design note |
| `infographics/png/` | The ten infographics, 1080 x 1350 px at 2x (2160 x 2700), LinkedIn portrait ratio |
| `infographics/pdf/` | One PDF per infographic |
| `infographics/sentinel-data-lake-normalization-infographics.pdf` | All ten in one PDF |
| `build/build.py` | Regenerates the canvas artboards |
| `build/render.py` | Regenerates the PNG and PDF files (Python 3, Playwright, pypdf) |
| `build/boards.json` | Artboard file, title and output name for each infographic |
| `build/canvas/project/` | Design canvas source: `canvas.json` and one `.dc.html` per artboard (`Main.dc.html` is infographic 01) |
| `solution-kit/` | Working files for the design note. See `solution-kit/README.md` |
| `product/` | Lake Hunt source. See `product/README.md` |
| `demo/index.html` | Static guided walkthrough: notebook 01 run, field review for a new table, approval, deploy and validation, drift fix, and a threat hunt. Synthetic data, one file |

### Solution kit

| Path | What it is |
|---|---|
| `registry/groups.example.yaml` | Grammar-group registry with four worked examples (sshd syslog, Palo Alto CEF, a custom JSON table, a raw custom table) |
| `registry/vocab.yaml` | Result vocabulary, role tokens, synonyms, null values |
| `generator/generate.py` | Turns the registry into KQL job queries and `notebook_config.json` |
| `generator/asim_expand.py` | Makes an ASIM parser's KQL lake-safe |
| `notebooks/01_inventory_and_mining.py` | Daily field inventory and template mining |
| `notebooks/02_index_longtail.py` | Hourly indexing of notebook groups into `HuntEntity_SPRK` and `HuntEvent_SPRK` |
| `notebooks/03_coverage.py` | Daily coverage, extraction rate and drift status |
| `mcp/tools.yaml` | Seven MCP tools with their KQL and agent instructions |
| `examples/five-sources/` | Five sources end to end (SecurityEvent, FortiGate CEF, sshd Syslog, a JSON app table, a raw VPN table): registry, generated KQL in `kql_out/` and `kql_out_reviewed/`, `run_demo.py` and `output.md` |
| `tests/` | `run_all.sh` offline checks, Kusto parse check, notebook tests, `lab-test-plan.md` |

### Lake Hunt (`product/`)

| Path | What it is |
|---|---|
| `app/` | FastAPI app: `engine/` (miner, indexer, hunt, coverage, guide), `providers/` (demo and Azure), `routers/` (REST API and MCP), `kit/` (copy of the solution kit generator, notebooks and tools), `static/` (web UI), `demo/` (synthetic data and registry), `data/catalog.json` (Content hub catalog) |
| `deploy/` | `main.bicep`, `roles.bicep`, `app-roles.json`, `deploy.ps1`, `deploy.sh` |
| `docs/screenshots/` | Eight UI screenshots: home, onboard fields, preview, hunt, approve, validate, coverage, hunt in dark mode |
| `docs/demo/lakehunt-demo.mp4` | Demo video, about 3 minutes |
| `docs/demo/lakehunt-hunt.gif` | The Hunt chapter of the demo |
| `docs/superpowers/` | Design spec and implementation plan for the 24 October UI work |
| `tests/` | pytest API and browser tests, Kusto checker, Spark parity check |
| `tools/` | `build_catalog.py`, `demo_architecture.py`, `record_demo.py` |
| `Dockerfile`, `requirements*.txt` | Container build and Python dependencies |

The demo data is synthetic and de-identified (documentation IP ranges, contoso.com names).

## How to read each infographic

1. **How ASIM works.** Read left to right: source tables feed source-specific parsers, which feed one unifying parser, which feeds analytics rules, hunting queries and workbooks. The dark bar under the first two columns marks the part that depends on the product and table schema; the pale bar marks the part that is the same for every product. The table below is one real mapping: Defender XDR columns on the left, ASIM field names on the right.
2. **Why ASIM stops at the lake.** Two vertical flows. The left (analytics tier) completes with check marks. The right (data lake tier) stops at the dashed box where the unifying parser is called, because lake KQL does not run functions; the grey steps below never happen. The quote is Microsoft's wording. The code block shows the same hunt rewritten as plain KQL for the lake.
3. **ASIM coverage at scale.** A long-tail curve: sources ranked by ingest volume left to right. The blue head is sources with an ASIM parser; the grey tail is sources without one. The shape is illustrative, not measured data. The rows below explain what happens to a source in each case.
4. **Methods compared.** One row per method. Filled circles in "Fields you get" mean more ASIM detail; filled circles in "Upkeep" mean more maintenance at hundreds of sources. The routing block below shows which method each kind of source should go to and which coverage tier it ends up in.
5. **Discovery pipeline.** Read top to bottom: scan every table, read three kinds of field, build a field inventory, classify values by pattern, produce a synonym dictionary and template registry, then write the entity index. Inventory rows are examples using documentation IP ranges.
6. **Confidence matrix.** Rows are entity types, columns are kinds of source. Dark blue is high confidence, light blue medium, dashed grey low. These are expected values based on how each field is found, not measurements. The panel below shows why value normalization matters for joins.
7. **Coverage tiers and drift.** The bar length in each tier shows how much a query can tell you about a source in that tier. The six cards are checks to run on every index build. The line chart is illustrative: extraction rate holds steady, then drops when a vendor changes a log format, which is what a drift alert catches.
8. **The ask to Microsoft.** Five numbered requests for the Sentinel product group. The dark table lists the custom work teams do today and whether the requests would remove it, reduce it, or leave it in place.
9. **Worked example: syslog.** The top panel shows raw sshd and sudo lines as they land in the Syslog table, with the first line's username and IP highlighted and the index values they become. Steps 1 to 5 are the KQL and registry entries that produce those values, in order: mine templates, record a template, generated per-template KQL, a value-regex catch-all for unmatched lines, and the hunt query against the entity index.
10. **Scaling to many raw sources.** The funnel shows effort narrowing from hosts to programs to templates to a fixed set of index columns (widths are illustrative). The grouping list shows the key used to group each kind of table. The five-card loop is the weekly cycle that moves formats from Tier 2 to Tier 1, and the stacked bars show that shift over time (illustrative shares). The table and rules cover what runs where and how to keep jobs fast.
