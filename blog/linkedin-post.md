New post on simple-security.ca: hunting across hundreds of log sources in the Microsoft Sentinel data lake.

The data lake makes it affordable to keep hundreds of third-party log sources for a year or more. Hunting across them is the hard part, because every source names the same things differently. ASIM solves this in the analytics tier, but its parsers are stored functions, and lake KQL can't run stored functions.

My approach is to normalize once, ahead of time, into a hunt index in the lake:

- Scheduled KQL jobs map approved sources with ASIM logic, registry rules and message templates.
- A lake notebook indexes sources nobody has reviewed yet, so a new table is searchable from day one.
- Two more notebooks propose mappings for new or changed sources and track coverage, so format changes get caught.
- Both index tables are rolled up by the hour, so a year of history stays small and cheap to search.
- An AI agent using the Sentinel data lake MCP server searches one set of ASIM field names instead of hundreds of tables.

At 1 TB a day the index adds about $440 to $490 a month on top of the lake's own ingestion and storage cost for the raw data. It has been deployed and run in my test tenant.

The design, solution kit, cost model, a browser walkthrough demo and a short video are all on GitHub.

Blog: https://simple-security.ca/2026/10/27/hunting-across-hundreds-of-log-sources-in-the-sentinel-data-lake/
GitHub: https://github.com/broglock/sentinel-data-lake-normalization
Walkthrough demo: https://broglock.github.io/sentinel-data-lake-normalization/demo/

#MicrosoftSentinel #ThreatHunting #KQL #ASIM #MicrosoftMVP
