# %% [markdown]
# # 01 Inventory and template mining
# Daily notebook job. For every lake table it samples recent rows and records, per field
# (typed column, key inside a JSON column, key in a key=value string): type, fill rate,
# value class shares, and a proposed ASIM name and role. For raw text columns it mines
# message templates by token masking (lake notebooks cannot install Drain3).
# Outputs: FieldInventory_SPRK, TemplateCandidates_SPRK. Proposals feed the registry review.

# %%
import json
import re
from datetime import datetime, timedelta, timezone

from pyspark.sql import functions as F
from pyspark.sql.types import StringType

SAMPLE_ROWS = 20000          # rows sampled per table
JSON_SAMPLE = 500            # rows parsed in Python for JSON and key=value keys
LOOKBACK = timedelta(days=1)
TEXT_COLUMNS = ["SyslogMessage", "RawData", "Message", "Msg", "EventMessage"]
SKIP_PREFIXES = ("HuntEntity", "HuntEvent", "HuntCoverage", "FieldInventory", "TemplateCandidates")
VOCAB_JSON = "{}"            # paste the vocab section of notebook_config.json here

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


def mine_templates(provider, name: str, since: datetime, top_n: int = 50):
    df = provider.read_table(name)
    text = next((c for c in TEXT_COLUMNS if c in df.columns), None)
    if not text:
        return None
    if "TimeGenerated" in df.columns:
        df = df.where(F.col("TimeGenerated") >= F.lit(since))
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


def run(spark, provider, vocab: dict, now: datetime | None = None):
    spark.conf.set("spark.sql.session.timeZone", "UTC")
    since = (now or datetime.now(timezone.utc)) - LOOKBACK
    inv, mined = [], None
    for name in provider.list_tables():
        if name.startswith(SKIP_PREFIXES):
            continue
        inv += inventory_table(provider, name, vocab, since)
        m = mine_templates(provider, name, since)
        if m is not None:
            mined = m if mined is None else mined.unionByName(m)
    inv_df = spark.createDataFrame(inv).withColumn("TimeGenerated", F.current_timestamp())
    provider.save_as_table(inv_df, "FieldInventory_SPRK", write_options={"mode": "overwrite"})
    if mined is not None:
        provider.save_as_table(mined.withColumn("TimeGenerated", F.current_timestamp()),
                               "TemplateCandidates_SPRK", write_options={"mode": "overwrite"})
    return inv_df, mined


# %%
if __name__ == "__main__" and VOCAB_JSON != "{}":
    from sentinel_lake.providers import MicrosoftSentinelProvider
    provider = MicrosoftSentinelProvider(spark)  # noqa: F821
    inv_df, mined = run(spark, provider, json.loads(VOCAB_JSON))  # noqa: F821
    # Proposals for review: high-fill fields whose values look like entities
    inv_df.where((F.col("FillRate") > 0.5) & (F.col("ProposedEntity") != "")).show(200, truncate=False)
