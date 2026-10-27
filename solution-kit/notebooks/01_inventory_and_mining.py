# %% [markdown]
# # 01 Inventory and template mining (change-driven)
# Daily notebook job. It reads only what changed:
#   - new tables, and tables whose column list changed since the last run (TableSchemas_SPRK)
#   - approved groups whose rows stopped matching: the share of rows with no entity, from the
#     "_stats" rows the index jobs write, is above UNMATCHED_SHARE. For those it mines only the
#     lines no approved template matches.
# Every other table is skipped, including tables whose proposals are already waiting for review:
# reading the column list is metadata only, so a skipped table costs nothing.
# For each table it does read, it samples recent rows and records, per field (typed column, key
# inside a JSON column, key in a key=value string): type, fill rate, value class shares, and a
# proposed ASIM name and role. For raw text columns it mines message templates by token masking
# (lake notebooks cannot install Drain3).
# Outputs (appended, one batch per run): FieldInventory_SPRK, TemplateCandidates_SPRK,
# TableSchemas_SPRK. Proposals feed the registry review.

# %%
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone

from pyspark.sql import functions as F
from pyspark.sql.types import StringType

SAMPLE_ROWS = 20000          # rows sampled per table
JSON_SAMPLE = 500            # rows parsed in Python for JSON and key=value keys
LOOKBACK = timedelta(days=1)
TEXT_COLUMNS = ["SyslogMessage", "RawData", "Message", "Msg", "EventMessage"]
SKIP_PREFIXES = ("HuntEntity", "HuntEvent", "HuntCoverage", "FieldInventory", "TemplateCandidates", "TableSchemas")
UNMATCHED_SHARE = 0.05       # approved group: re-mine when more rows than this produce no entity
CONFIG_JSON = "{}"           # paste notebook_config.json here (groups, engines and vocab)
SCHEMA_TABLE = "TableSchemas_SPRK"
ENTITY_TABLES = ["HuntEntity_SPRK", "HuntEntity_KQL"]

VALUE_CLASSES = {
    "ip": r"^\[?(\d{1,3}(\.\d{1,3}){3}|[0-9a-fA-F:]*:[0-9a-fA-F:]+)\]?(:\d+)?$",
    "upn": r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$",
    "windows_user": r"^[A-Za-z0-9._-]+\\[A-Za-z0-9._$-]+$",
    "sid": r"^S-1-\d+(-\d+)+$",
    "hash": r"^([a-fA-F0-9]{32}|[a-fA-F0-9]{40}|[a-fA-F0-9]{64})$",
    "url": r"^(https?|hxxps?)://",
    "fqdn": r"^([A-Za-z0-9-]+\.)+[A-Za-z]{2,}$",
    "guid": r"^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$",
}
CLASS_TO_ENTITY = {"ip": "ip", "upn": "user", "windows_user": "user", "sid": "user",
                   "hash": "hash", "url": "url", "fqdn": "host"}
MASKS = [
    (r"\b\d{1,3}(?:\.\d{1,3}){3}\b", "<IP>"),
    (r"\b[0-9a-fA-F]{8}-[0-9a-fA-F-]{27}\b", "<UUID>"),
    (r"\b[0-9a-fA-F]{16,}\b", "<HEX>"),
    (r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b", "<EMAIL>"),
    (r"(?:/[\w.-]+)+", "<PATH>"),
    (r"\b\d+\b", "<NUM>"),
]


# %%
def squash(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def propose(name: str, vocab: dict) -> tuple[str, str]:
    """Proposed ASIM field and role from a field name (review required)."""
    s = squash(name.split(".")[-1])
    asim = next((a for a, syn in vocab.get("synonyms", {}).items() if s in [squash(x) for x in syn]), "")
    role = "Unknown"
    for r in ("Src", "Dst", "Actor", "Target", "Dvc"):
        if any(tok in s for tok in vocab.get("role_tokens", {}).get(r, [])):
            role = r
            break
    return asim, role


def classify_values(values: list[str]) -> dict:
    n = max(len(values), 1)
    return {c: sum(1 for v in values if v and re.search(p, v)) / n for c, p in VALUE_CLASSES.items()}


def flatten_json(obj, prefix=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from flatten_json(v, f"{prefix}.{k}" if prefix else k)
    elif isinstance(obj, list):
        for v in obj[:5]:
            yield from flatten_json(v, prefix + "[]")
    else:
        yield prefix, None if obj is None else str(obj)


KV = re.compile(r"(?:^|[\s;|,])([A-Za-z][\w.-]{0,40})=(\"[^\"]*\"|[^\s;|,]*)")


def inventory_table(provider, name: str, vocab: dict, since: datetime) -> list[dict]:
    df = provider.read_table(name)
    if "TimeGenerated" in df.columns:
        df = df.where(F.col("TimeGenerated") >= F.lit(since))
    df = df.limit(SAMPLE_ROWS).cache()
    n = df.count()
    rows = []
    if n == 0:
        return rows
    sample = [r.asDict() for r in df.limit(JSON_SAMPLE).collect()]
    for field in df.schema.fields:
        col = field.name
        filled = df.where(F.col(col).isNotNull() & (F.col(col).cast("string") != "")).count() / n
        vals = [None if r.get(col) is None else str(r.get(col)) for r in sample]
        cls = classify_values([v for v in vals if v])
        asim, role = propose(col, vocab)
        top = max(cls, key=cls.get) if cls else ""
        rows.append({"TableName": name, "FieldPath": col, "Kind": "column", "DataType": field.dataType.simpleString(),
                     "FillRate": round(filled, 4), "TopValueClass": top if cls.get(top, 0) >= 0.5 else "",
                     "TopValueClassShare": round(cls.get(top, 0), 4), "ProposedAsim": asim, "ProposedRole": role,
                     "ProposedEntity": CLASS_TO_ENTITY.get(top, "") if cls.get(top, 0) >= 0.5 else "",
                     "SampleValue": next((v for v in vals if v), "")[:200]})
        texts = [v for v in vals if v]
        # keys inside JSON values
        if isinstance(field.dataType, StringType) and texts and sum(t.lstrip().startswith("{") for t in texts) / len(texts) > 0.5 \
                or field.dataType.simpleString().startswith(("map", "struct")):
            keyvals: dict[str, list] = {}
            for t in texts:
                try:
                    obj = json.loads(t) if isinstance(t, str) else t
                except ValueError:
                    continue
                for path, v in flatten_json(obj):
                    keyvals.setdefault(path, []).append(v)
            rows += key_rows(name, col, "json", keyvals, len(texts), vocab)
        # keys in key=value strings (CEF extensions, appliance logs)
        elif texts and sum(1 for t in texts if len(KV.findall(t)) >= 2) / len(texts) > 0.5:
            keyvals = {}
            for t in texts:
                for k, v in KV.findall(t):
                    keyvals.setdefault(k, []).append(v.strip('"'))
            rows += key_rows(name, col, "kv", keyvals, len(texts), vocab)
    df.unpersist()
    return rows


def key_rows(table, col, kind, keyvals, n, vocab):
    out = []
    for path, vals in keyvals.items():
        cls = classify_values([v for v in vals if v])
        top = max(cls, key=cls.get) if cls else ""
        asim, role = propose(path, vocab)
        out.append({"TableName": table, "FieldPath": f"{col}.{path}", "Kind": kind, "DataType": "string",
                    "FillRate": round(sum(1 for v in vals if v) / max(n, 1), 4),
                    "TopValueClass": top if cls.get(top, 0) >= 0.5 else "",
                    "TopValueClassShare": round(cls.get(top, 0), 4), "ProposedAsim": asim, "ProposedRole": role,
                    "ProposedEntity": CLASS_TO_ENTITY.get(top, "") if cls.get(top, 0) >= 0.5 else "",
                    "SampleValue": next((v for v in vals if v), "")[:200]})
    return out


def mine_templates(provider, name: str, since: datetime, top_n: int = 50, skip_regex: list | None = None,
                   spark_filter: str | None = None):
    """Template candidates for a text table. skip_regex: approved templates, whose lines are
    left out so only unmatched lines are mined."""
    df = provider.read_table(name)
    text = next((c for c in TEXT_COLUMNS if c in df.columns), None)
    if not text:
        return None
    if "TimeGenerated" in df.columns:
        df = df.where(F.col("TimeGenerated") >= F.lit(since))
    if spark_filter:
        df = df.where(F.expr(spark_filter))
    for r in skip_regex or []:
        df = df.where(~F.col(text).rlike(r))
    key = F.col("ProcessName") if "ProcessName" in df.columns else F.split(F.trim(F.col(text)), r"\s+").getItem(0)
    masked = F.col(text)
    for pattern, token in MASKS:
        masked = F.regexp_replace(masked, pattern, token)
    t = (df.limit(SAMPLE_ROWS * 5)
           .select(F.lit(name).alias("TableName"), key.cast("string").alias("GroupKey"), masked.alias("Template"),
                   F.col(text).alias("Example"))
           .groupBy("TableName", "GroupKey", "Template").agg(F.count("*").alias("Lines"), F.first("Example").alias("Example")))
    from pyspark.sql.window import Window
    w = Window.partitionBy("GroupKey").orderBy(F.desc("Lines"))
    return t.withColumn("Rank", F.row_number().over(w)).where(F.col("Rank") <= top_n)


def fingerprint(df) -> str:
    """Column names and types: read from the table metadata, no rows scanned."""
    cols = sorted(f"{f.name}:{f.dataType.simpleString()}" for f in df.schema.fields)
    return hashlib.sha256("|".join(cols).encode()).hexdigest()


def last_fingerprints(provider) -> dict:
    try:
        rows = provider.read_table(SCHEMA_TABLE).groupBy("TableName").agg(
            F.max_by("Fingerprint", "TimeGenerated").alias("Fingerprint")).collect()
    except Exception:  # first run
        return {}
    return {r["TableName"]: r["Fingerprint"] for r in rows}


def unmatched_shares(provider, since: datetime) -> dict:
    """Per group: share of rows read in the last day that no approved rule matched (from _stats rows)."""
    out = {}
    for t in ENTITY_TABLES:
        try:
            df = provider.read_table(t)
        except Exception:
            continue
        rows = (df.where((F.col("EntityType") == "_stats") & (F.col("Hour") >= F.lit(since)))
                  .groupBy("SourceGroup", "Role").agg(F.sum("Count").alias("n")).collect())
        for r in rows:
            out.setdefault(r["SourceGroup"], {})[r["Role"]] = int(r["n"] or 0)
    # text groups with templates: lines no template matched; structured groups: rows with no entity
    return {g: 1 - v.get("RowsTemplateMatched", v.get("RowsWithEntity", 0)) / v["RowsRead"]
            for g, v in out.items() if v.get("RowsRead")}


def plan(provider, cfg: dict, since: datetime) -> list[dict]:
    """Which tables to read today, and why. Everything else is skipped."""
    prev = last_fingerprints(provider)
    unmatched = unmatched_shares(provider, since)
    by_table: dict[str, list] = {}
    for g in cfg.get("groups", []):
        by_table.setdefault(g["table"], []).append(g)
    work = []
    for name in provider.list_tables():
        if name.startswith(SKIP_PREFIXES):
            continue
        fp = fingerprint(provider.read_table(name))
        groups = by_table.get(name, [])
        drifting = [g for g in groups if g.get("engine") == "kql_job" and unmatched.get(g["id"], 0) > UNMATCHED_SHARE]
        reason = ("new table" if name not in prev else "schema changed" if prev[name] != fp
                  else "unmatched lines" if drifting else None)
        if reason:
            work.append({"table": name, "fingerprint": fp, "reason": reason, "drifting": drifting})
    return work


def run(spark, provider, cfg: dict, now: datetime | None = None):
    spark.conf.set("spark.sql.session.timeZone", "UTC")
    now = now or datetime.now(timezone.utc)
    since = now - LOOKBACK
    vocab = cfg.get("vocab", cfg)
    inv, mined, done = [], None, []
    for w in plan(provider, cfg, since):
        name = w["table"]
        if w["reason"] == "unmatched lines":
            # approved groups whose lines stopped matching: mine only the lines no template matches
            for g in w["drifting"]:
                m = mine_templates(provider, name, since, skip_regex=[t["regex_plain"] for t in g.get("templates", [])],
                                   spark_filter=g.get("spark_filter"))
                if m is not None:
                    m = m.withColumn("SourceGroup", F.lit(g["id"]))
                    mined = m if mined is None else mined.unionByName(m, allowMissingColumns=True)
        else:
            inv += inventory_table(provider, name, vocab, since)
            m = mine_templates(provider, name, since)
            if m is not None:
                mined = m if mined is None else mined.unionByName(m, allowMissingColumns=True)
        done.append({"TableName": name, "Fingerprint": w["fingerprint"], "Reason": w["reason"]})
    stamp = F.current_timestamp()
    inv_df = spark.createDataFrame(inv).withColumn("TimeGenerated", stamp) if inv else None
    if inv_df is not None:
        provider.save_as_table(inv_df, "FieldInventory_SPRK", write_options={"mode": "append"})
    if mined is not None:
        provider.save_as_table(mined.withColumn("TimeGenerated", stamp), "TemplateCandidates_SPRK",
                               write_options={"mode": "append"})
    if done:
        provider.save_as_table(spark.createDataFrame(done).withColumn("TimeGenerated", stamp), SCHEMA_TABLE,
                               write_options={"mode": "append"})
    return inv_df, mined, done


# %%
if __name__ == "__main__" and CONFIG_JSON != "{}":
    from sentinel_lake.providers import MicrosoftSentinelProvider
    provider = MicrosoftSentinelProvider(spark)  # noqa: F821
    inv_df, mined, done = run(spark, provider, json.loads(CONFIG_JSON))  # noqa: F821
    print("read:", [(d["TableName"], d["Reason"]) for d in done])
    if inv_df is not None:  # proposals for review: high-fill fields whose values look like entities
        inv_df.where((F.col("FillRate") > 0.5) & (F.col("ProposedEntity") != "")).show(200, truncate=False)
