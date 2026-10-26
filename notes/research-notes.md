# Sentinel data lake normalization: research notes

Last checked: 16 October 2026

## Facts and sources

### ASIM model
- ASIM schemas are product-neutral field definitions (Network Session, Authentication, Process Event, File Event, Registry Event, DNS, Web Session, Audit Event, Alert (preview), and others).
- Source-specific parsers are KQL functions written per product per schema against one table's columns, filter values (DeviceVendor/DeviceProduct, EventID) or message formats.
- Unifying parsers (`_Im_<Schema>`, `im<Schema>`) union the source-specific parsers. Analytics rules, hunting queries and workbooks in the ASIM content are written against the unifying parsers.
- Ingest-time option: DCR transforms into native ASim tables (ASimProcessEventLogs, ASimNetworkSessionLogs, ASimFileEventLogs, ASimRegistryEventLogs and others).
- A source with no parser gets nothing from ASIM. A schema change on the source table usually makes a parser return no rows instead of failing.
- June 2026 ASIM update: new parsers for Azure Firewall, Key Vault, AWS CloudTrail (EC2, S3, IAM) and 10+ third-party products; new schemas including Asset Entities.
  - https://techcommunity.microsoft.com/blog/microsoftsentinelblog/introducing-new-additions-to-microsoft-sentinel-normalization-and-asim/4524584
  - https://learn.microsoft.com/en-us/azure/sentinel/normalization-about-schemas
  - https://learn.microsoft.com/en-us/azure/sentinel/normalization-parsers-overview

### Data lake KQL limits
- "Using out-of-the-box or custom functions isn't supported in KQL queries against the data lake." This covers ASIM parsers.
- Not supported: externaldata(), adx(), arg(), ingestion_time(), estimate_data_size(); legacy tables such as AzureDiagnostics.
- 15-minute latency to query; interactive results capped at 500,000 rows or 64 MB; 30 queries/min and 10 concurrent per tenant (interactive and async).
  - https://learn.microsoft.com/en-us/azure/sentinel/datalake/kql-queries
  - https://learn.microsoft.com/en-us/azure/sentinel/datalake/kql-troubleshoot
- Community: Precursor Security (28 Sep 2026) reads the docs the same way; parser-based hunts need rewriting against raw tables.
  - https://www.precursorsecurity.com/blog/sentinel-data-lake-threat-hunting

### Microsoft direction (What's new, July 2025 to September 2026)
- No item covers ASIM in the data lake, function support in the lake, or normalized lake tables.
- Relevant capabilities: data lake GA (Sep 2025), Sentinel graph (preview), transform data with filter and split (preview, Apr 2026), data federation (preview), custom graphs, Fabric/OneLake mirroring and Fabric custom analytics (Sep 2026).
  - https://learn.microsoft.com/en-us/azure/sentinel/whats-new

## To verify in a lab before customer claims
- Whether query-scoped `let` definitions run in lake KQL.
- Whether `union *` and `where * has` run in lake KQL.
- Whether `reduce` runs in lake KQL.
- Whether filter-and-split transforms can write ASIM-shaped columns into lake-tier tables.
- Which ASim native tables can be set to the lake tier.
- Current Sentinel notebook provider API (list_databases, list_tables, read_table).

## Design summary (methods)
1. Free-text search (union *, where * has) for literal indicators. No maintenance.
2. Inline Microsoft's ASIM parser logic (synced from the Azure-Sentinel GitHub YAML) for sources with parsers. Full ASIM depth.
3. Discovery scan: typed columns, keys inside dynamic/JSON columns, key=value strings; classify by value pattern; build one synonym dictionary.
4. Entity index: one narrow table with ASIM column names (SrcIpAddr, DstIpAddr, ActorUsername, DvcHostname, Url, FileHash, Domain), built by notebook or KQL job.
5. Syslog and raw text: template mining (Drain3 or KQL reduce) per ProcessName, plus value regex for unmatched lines.
6. Value normalization: lowercase, split domain/user, SID resolution, FQDN to short host.
7. Coverage report per source: extraction rate, fill rate per entity, unmapped high-fill columns, template match rate, ground-truth samples, canary tests, drift alerts. Tier each source: ASIM-parsed, entity-only, search-only.
8. Ingest-time DCR normalization only for the top sources by volume. Per-source DCRs for hundreds of sources is not maintainable.
