# Cost model at 1 TB/day

26 October 2026, revised 27 October 2026 for change-driven notebooks. A planning model, not a measurement. Prices are the Microsoft preview list prices in USD for East US: data lake query $0.005 per GB analyzed, advanced data insights (notebooks) $0.15 per compute hour, lake storage $0.026 per GB per month, lake ingestion $0.05 per GB. Confirm current regional prices on the Sentinel pricing page before quoting a customer. 1 TB = 1,000 GB, 30-day month.

## Billing basis

- KQL jobs: per GB of uncompressed data scanned.
- Notebooks: compute hours = vCores in the pool x time the job runs. Pools of 12, 32 and 80 vCores (an older Learn page lists 4, 8 and 16).
- Storage: billed on compressed size, 6:1.

**Current figure: about $830 to $890 a month at 1 TB/day** (change-driven notebooks, hourly entity rollup, one year of index storage). The sections below show how the design got there: the original always-on notebooks, the index size problem, the rollup, then the change-driven notebooks.

## Assumptions

| Item | Value |
|---|---|
| Lake ingest | 1 TB/day uncompressed |
| Average event size | 1 KB, so about 1 billion events/day |
| Entities per event | 3 |
| Structured share (KQL jobs) | 70% |
| Free text and long tail (notebook 02) | 30%, about 12.5 GB per hourly run |
| KQL job lookback | 75 minutes per hourly run (25% overlap) |
| Jobs per structured source | 2 (HuntEntity and HuntEvent; a KQL job writes one table) |
| HuntEntity row | about 250 bytes uncompressed |
| HuntEvent row | about 400 bytes uncompressed, Tier 1 sources only |

## Original design: always-on notebooks

Notebook 01 sampled every table daily, notebook 02 indexed all free text hourly, and notebook 03 re-read source data for coverage.


| Workload | Calculation | Per month |
|---|---|---|
| KQL jobs | 700 GB x 2 jobs x 1.25 overlap = 1,750 GB/day scanned | $263 |
| Notebook 02, low | 12 vCores, 10 min per run, 720 runs = 1,440 compute hours | $216 |
| Notebook 02, middle | 12 vCores, 20 min per run = 2,880 compute hours | $432 |
| Notebook 02, high | 32 vCores, 15 min per run = 5,760 compute hours | $864 |
| Notebook 01, sampled | 32 vCores, 30 min daily = 480 compute hours | $72 |
| Notebook 01, full scan | 32 vCores, 2 h daily = 1,920 compute hours | $288 |
| Notebook 03 | 12 vCores, 20 min daily = 120 compute hours | $18 |
| **Build total** | | **about $570 to $1,430** |

Notebook 02 runtime is the largest unknown. It depends on free-text volume, the number of templates and Spark session start time.

## Index size: the bigger cost

At one row per entity occurrence the index is about as large as the raw data:

| Table | Per day, uncompressed |
|---|---|
| HuntEntity: 3 billion rows x 250 B | 750 GB |
| HuntEvent: 700 million rows x 400 B | 280 GB |
| Total | 1,030 GB |

| Effect | Per month |
|---|---|
| Storage at one year retention, steady state | about $1,630 |
| Lake ingestion on index writes, if charged (not confirmed) | about $1,545 |
| One hunt over a year of HuntEntity (274 TB scanned) | $1,369 per hunt |
| One hunt over a year of raw data (365 TB scanned) | $1,825 per hunt |

For comparison, the raw lake itself costs about $1,500/month to ingest and about $1,580/month to store for a year at this volume. At this grain the index roughly doubles the lake bill and saves only 25% per hunt.

## Hourly entity rollup

Store one HuntEntity row per (hour, EntityType, ValueNorm, Role, SourceGroup) with Count, FirstSeen, LastSeen and a few sample SourceRecordKeys, instead of one row per occurrence. If distinct tuples are 2% of occurrences:

| Item | Value |
|---|---|
| Rollup size | about 18 GB/day uncompressed |
| Storage at one year | about $28/month |
| One hunt over a year of the rollup | about $33 |
| Pivot to raw | scan only the matched table and hours |

HuntEvent stays per event but should be limited to the sources and schemas analysts actually query in ASIM form, or rolled up the same way.

The 2% figure is the assumption to test first: measure distinct tuples per hour on real data.

## Current design: change-driven notebooks

A mapping is decided once. After that the notebooks stop touching the source:

- Notebook 01 reads only new tables, changed schemas and the lines the index jobs counted as unmatched. Approved, high-confidence groups are skipped.
- Approved message templates are written as KQL `parse` or `extract` and move into the KQL jobs. Notebook 02 keeps only unreviewed groups, through the value classifier.
- Each index job writes its own counts (rows read, rows with an entity, rows matching a template). Notebook 03 builds the coverage and drift report from those counts and reads no source data.
- Every job reads only the new hour. Nothing already indexed is read again. Windows are aligned to the hour with a 15-minute delay, so there is no overlap.

Applying an approved mapping to each new event cannot be removed: the index is stored rows, so every new hour passes through a job once. That cost now sits in KQL jobs, billed per GB scanned.

Assumptions for steady state: 95% of volume in approved groups (KQL jobs), 5% unreviewed (notebook 02, about 2 GB per hourly run).

| Item | Calculation | Per month |
|---|---|---|
| KQL jobs | 950 GB x 2 jobs (HuntEntity, HuntEvent) = 1,900 GB/day scanned | $285 |
| Notebook 02, unreviewed groups only | 12 vCores, 3 to 5 min per run, 720 runs = 432 to 720 compute hours | $65 to $108 |
| Notebook 01, new and changed sources only | 12 vCores, 10 to 20 min daily = 60 to 120 compute hours | $9 to $18 |
| Notebook 03, from job counts | 12 vCores, 5 min daily = 30 compute hours | $5 |
| HuntEntity rollup storage, one year | | $28 |
| HuntEvent storage, one year, every Tier 1 event (280 GB/day uncompressed) | | $443 |
| **Total** | | **about $830 to $890** |

Compared with the original design with the rollup ($1,040 to $1,900), notebook compute falls from $306 to $1,170 a month to $79 to $131. HuntEvent storage is now the largest item; limiting HuntEvent to the schemas analysts query in ASIM form (for example authentication and network sessions) is the next saving.

Not included: lake ingestion on index writes, if charged (about $447/month for 298 GB/day), and hunts against the index. During onboarding waves, when many sources are unreviewed at once, notebook 02 costs move back toward the original figures until the new groups are approved.

## Controls

- Move every approved group, templates included, into KQL jobs; keep notebook 02 for unreviewed groups only.
- Smallest notebook pool that finishes inside the hour.
- Notebook 01 reads only new tables, changed schemas and unmatched lines; it skips approved groups.
- Build the coverage report from job counts, not from source tables.
- Filter rows by template keyword before token masking in notebook 02.
- Incremental windows only: aligned hours, never history.
- Set data lake usage thresholds. Since April 2026 they can block new queries and jobs when exceeded.

## Lab tests to add

1. Notebook 02 runtime and session start time per run, on the 12 vCore pool, for a realistic share of unreviewed data.
2. Whether KQL job and notebook output written to lake tables is billed as lake ingestion.
3. Distinct (hour, entity, role, source group) tuples as a share of entity occurrences.
4. Whether a time filter on lake tables reduces the GB billed for a query.
5. Whether approved templates written as KQL `parse`/`extract` give the same rows as the notebook (the parity check in `product/tests/parity_spark.py` covers the current split).

## Sources

- Microsoft Sentinel billing: https://learn.microsoft.com/azure/sentinel/billing
- Sentinel data lake pricing (preview): https://techcommunity.microsoft.com/blog/microsoft-security-blog/-/4433919
- Threshold enforcement: https://charbelnemnom.com/sentinel-cost-estimation-and-optimization/
