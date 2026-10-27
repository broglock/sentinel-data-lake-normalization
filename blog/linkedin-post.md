This is one of those holy grail topics for SIEM architects: one search across every log source, with the same field names, no matter how each vendor writes its logs.

The Microsoft Sentinel data lake makes it affordable to keep hundreds of third-party log sources for a year or more. Hunting across them is the hard part, because every source names the same things differently. ASIM solves this in the analytics tier, but its parsers are stored functions, and lake KQL can't run stored functions.

My approach is to normalize once, ahead of time, into a hunt index in the lake.

Read the blog: https://simple-security.ca/2026/10/27/hunting-across-hundreds-of-log-sources-in-the-sentinel-data-lake/
Try the demo: https://broglock.github.io/sentinel-data-lake-normalization/demo/

Judge for yourself if this is a good approach.
