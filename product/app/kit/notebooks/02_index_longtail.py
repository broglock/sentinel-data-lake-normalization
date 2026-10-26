# %% [markdown]
# # 02 Index long tail
# Indexes every registry group with `engine: notebook` into HuntEntity_SPRK (and
# HuntEvent_SPRK for Tier 1 groups). Schedule as a notebook job, hourly.
# Uses only PySpark and the Sentinel Provider library (no pip packages in lake notebooks).
#
# Inputs: notebook_config.json produced by generator/generate.py. Paste its content into
# CONFIG_JSON below, or keep it in a lake table and read it from there.

# %%
import json
from datetime import datetime, timedelta, timezone

from pyspark.sql import DataFrame, functions as F
from pyspark.sql.types import StringType

CONFIG_JSON = "{}"           # paste notebook_config.json here
WINDOW = timedelta(hours=1)  # one aligned hour per run
DELAY = timedelta(minutes=15)
ENTITY_TABLE = "HuntEntity_SPRK"
EVENT_TABLE = "HuntEvent_SPRK"

# %%
def esc_sql(s: str) -> str:
    """Escape a string for a Spark SQL single-quoted literal."""
    return s.replace("\\", "\\\\").replace("'", "\\'")


def field_col(df: DataFrame, rule: dict):
    """Column expression for a registry field rule (column or JSON path)."""
    if "column" in rule:
        c = F.col(rule["column"]).cast("string")
        if "when_label" in rule:
            lab = rule["when_label"]
            c = F.when(F.col(lab["column"]) == lab["equals"], c).otherwise(F.lit(""))
        return c
    head, *rest = rule["path"].split(".")
    if isinstance(df.schema[head].dataType, StringType):
        return F.get_json_object(F.col(head), "$." + ".".join(rest))
    return F.col(rule["path"]).cast("string")


def ent(entity: str, role: str, value, layer: str, tier: int):
    return F.struct(F.lit(entity).alias("EntityType"), F.lit(role).alias("Role"),
                    value.cast("string").alias("Value"), F.lit(layer).alias("MappingLayer"),
                    F.lit(int(tier)).alias("MappingTier"))


def map_col(df: DataFrame, rule: dict):
    """A lookup from source values to ASIM values, e.g. EventID 4625 -> Failure."""
    src = field_col(df, rule)
    out = None
    for k, v in rule["map"].items():
        out = F.when(src == str(k), v) if out is None else out.when(src == str(k), v)
    return out.otherwise(rule.get("default", ""))


def result_col(df: DataFrame, group: dict, vocab: dict):
    rule = group.get("result")
    if not rule:
        return F.lit("")
    if "map" in rule:
        return map_col(df, rule)
    v = vocab["result_vocab"][rule.get("vocab", "default")]
    r = F.lower(F.trim(field_col(df, rule)))
    out = F.when(r.isin([str(w) for w in v.get("Success", [])]), "Success") \
           .when(r.isin([str(w) for w in v.get("Failure", [])]), "Failure") \
           .when(r.isin([str(w) for w in v.get("Partial", [])]), "Partial")
    if v.get("http_status"):
        n = r.cast("int")
        out = out.when(n.between(100, 399), "Success").when(n.between(400, 599), "Failure")
    return out.otherwise("NA")


def event_type_col(df: DataFrame, group: dict):
    rule = group.get("event_type")
    if not rule:
        return F.lit("")
    if "constant" in rule:
        return F.lit(rule["constant"])
    if "map" in rule:
        return map_col(df, rule)
    return field_col(df, rule)


def with_meta(df: DataFrame, group: dict, event_type, event_result) -> DataFrame:
    return (df.select(F.explode("_ents").alias("_e"), "EventStartTime", "SourceRecordKey")
              .select("EventStartTime", "SourceRecordKey",
                      F.lit(group["table"]).alias("SourceTable"), F.lit(group["id"]).alias("SourceGroup"),
                      F.lit(group.get("vendor", "")).alias("EventVendor"),
                      F.lit(group.get("product", "")).alias("EventProduct"),
                      F.lit(group.get("schema", "")).alias("EventSchema"),
                      event_type.alias("EventType"), event_result.alias("EventResult"),
                      "_e.EntityType", "_e.Role", "_e.Value", "_e.MappingLayer", "_e.MappingTier"))


def classifier_struct(etype: str):
    """One-argument lambda for F.transform (a default argument would read as an index)."""
    return lambda x: ent(etype, "Unknown", x, "classifier", 2)


def entity_rows(base: DataFrame, group: dict, cfg: dict) -> DataFrame:
    vocab, classifier = cfg["vocab"], cfg["classifier"]
    tier = int(group.get("tier", 2))
    parts = []
    fields = [f for f in group.get("fields", []) if f.get("entity")]
    consts = [c for c in group.get("constant_entities", []) if c.get("entity")]
    text = group.get("text_column")

    if fields or (consts and not text):
        b = base.withColumn("_et", event_type_col(base, group)).withColumn("_er", result_col(base, group, vocab))
        arr = [ent(f["entity"], f.get("role", "Unknown"), field_col(base, f), "registry", tier) for f in fields]
        arr += [ent(c["entity"], c["role"], field_col(base, c), "registry", tier) for c in consts]
        b = b.withColumn("_ents", F.array(*arr))
        parts.append(b.select(F.explode("_ents").alias("_e"), "EventStartTime", "SourceRecordKey", "_et", "_er")
                      .select("EventStartTime", "SourceRecordKey",
                              F.lit(group["table"]).alias("SourceTable"), F.lit(group["id"]).alias("SourceGroup"),
                              F.lit(group.get("vendor", "")).alias("EventVendor"),
                              F.lit(group.get("product", "")).alias("EventProduct"),
                              F.lit(group.get("schema", "")).alias("EventSchema"),
                              F.col("_et").cast("string").alias("EventType"), F.col("_er").alias("EventResult"),
                              "_e.EntityType", "_e.Role", "_e.Value", "_e.MappingLayer", "_e.MappingTier"))

    if text:
        templates = group.get("templates", []) or []
        matched_any = F.lit(False)
        for t in templates:
            rx = t["regex_plain"]
            hit = F.col(text).rlike(rx)
            matched_any = matched_any | hit
            b = base.where(F.col(text).contains(t["match"]) & hit)
            for name, idx in t["group_index"].items():
                b = b.withColumn(name, F.regexp_extract(F.col(text), rx, int(idx)))
            t_tier = int(t.get("tier", tier))
            arr = [ent(s["entity"], s.get("role", "Unknown"), F.col(name), "template", t_tier)
                   for name, s in (t.get("slots") or {}).items() if s and s.get("entity")]
            if not fields:
                arr += [ent(c["entity"], c["role"], field_col(base, c), "template", t_tier) for c in consts]
            parts.append(with_meta(b.withColumn("_ents", F.array(*arr)), group,
                                   F.lit(t.get("event_type", "")), F.lit(t.get("event_result", ""))))

        rest = base.where(~matched_any) if templates else base
        arrays = []
        for i, (etype, pattern) in enumerate(classifier):
            extracted = F.expr(f"regexp_extract_all(`{text}`, '{esc_sql(pattern)}', 1)")
            arrays.append(F.transform(F.coalesce(extracted, F.array().cast("array<string>")),
                                      classifier_struct(etype)))
        r = rest.withColumn("_ents", F.flatten(F.array(*arrays)))
        parts.append(with_meta(r, group, F.lit(""), F.lit("")))
        if consts and not fields:
            rc = rest.withColumn("_ents", F.array(*[ent(c["entity"], c["role"], field_col(base, c), "registry", 2)
                                                   for c in consts]))
            parts.append(with_meta(rc, group, F.lit(""), F.lit("")))

    out = parts[0]
    for p in parts[1:]:
        out = out.unionByName(p)
    return normalize(out, cfg["vocab"].get("null_values", []))


def normalize(df: DataFrame, nulls: list) -> DataFrame:
    """Same rules as NORMALIZE_TAIL in generate.py."""
    v = F.trim(F.regexp_replace(F.col("Value"), "[\"']", ""))
    df = df.withColumn("Value", v).where(~F.lower(F.col("Value")).isin([str(n) for n in nulls]) & F.col("Value").isNotNull())
    refang = F.regexp_replace(F.regexp_replace(F.regexp_replace(F.col("Value"), "hxxp", "http"), r"\[\.\]", "."), r"\[:\]", ":")
    df = df.withColumn("Value", F.when(F.col("EntityType").isin("url", "domain"), refang).otherwise(F.col("Value")))
    et, val = F.col("EntityType"), F.col("Value")
    vtype = (F.when(et == "ip", F.when(F.size(F.split(val, ":")) >= 3, "IPv6").otherwise("IPv4"))
              .when((et == "user") & val.rlike(r"^S-1-\d+(-\d+)+$"), "SID")
              .when((et == "user") & val.rlike(r"^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$"), "AADID")
              .when((et == "user") & val.contains("\\"), "Windows")
              .when((et == "user") & val.startswith("CN="), "DN")
              .when((et == "user") & val.rlike(r"^[^@\s]+@[^@\s]+\.[^@\s]+$"), "UPN")
              .when(et == "user", "Simple")
              .when(et == "host", F.when(val.contains("."), "FQDN").otherwise("Hostname"))
              .when(et == "hash", F.when(F.length(val) == 32, "MD5").when(F.length(val) == 40, "SHA1")
                                   .when(F.length(val) == 64, "SHA256").otherwise("Other"))
              .when(et == "url", "URL").when(et == "email", "UPN").when(et == "domain", "FQDN")
              .otherwise("Other"))
    df = df.withColumn("ValueType", vtype)
    vt = F.col("ValueType")
    norm = (F.when(vt == "IPv4", F.regexp_extract(val, r"(\d{1,3}(?:\.\d{1,3}){3})", 1))
             .when(vt == "IPv6", F.lower(F.regexp_replace(F.split(val, "%").getItem(0), r"[\[\]]", "")))
             .when(vt.isin("SID", "AADID"), F.upper(val))
             .when(vt == "Windows", F.lower(F.split(val, r"\\").getItem(1)))
             .when(vt == "DN", F.lower(F.regexp_extract(val, r"^CN=([^,]+)", 1)))
             .when((et == "user") & (vt == "UPN"), F.lower(F.split(val, "@").getItem(0)))
             .when((et == "host") & val.contains("\\"), F.lower(F.split(val, r"\\").getItem(1)))
             .when((et == "host") & (vt == "FQDN"), F.lower(F.split(val, r"\.").getItem(0)))
             .when(et == "domain", F.lower(F.regexp_replace(val, r"\.$", "")))
             .otherwise(F.lower(val)))
    df = df.withColumn("ValueNorm", norm)
    octets_ok = F.forall(F.split(F.col("ValueNorm"), r"\."), lambda o: o.cast("int").between(0, 255))
    is_ipv4_text = val.rlike(r"^\d{1,3}(\.\d{1,3}){3}$")
    df = df.where(~((vt == "IPv4") & ~(octets_ok & (F.col("ValueNorm") != ""))))
    df = df.where(~((et == "host") & is_ipv4_text))
    df = df.where(~((et == "hash") & (vt == "Other")))
    return df.where(F.col("ValueNorm").isNotNull() & (F.col("ValueNorm") != ""))


def event_rows(base: DataFrame, group: dict, cfg: dict) -> DataFrame | None:
    """HuntEvent rows for Tier 1 groups with structured field rules."""
    if int(group.get("tier", 2)) != 1 or not group.get("fields"):
        return None
    nulls = [str(n) for n in cfg["vocab"].get("null_values", [])]

    def clean(name: str, col):
        """Null markers become empty; IP columns lose ports and brackets (same rules as HuntEntity)."""
        c = F.trim(col)
        c = F.when(F.lower(c).isin(nulls), F.lit("")).otherwise(c)
        if name.endswith("IpAddr"):
            c = F.when(F.size(F.split(c, ":")) >= 3, F.lower(F.regexp_replace(F.split(c, "%").getItem(0), r"[\[\]]", ""))) \
                 .otherwise(F.regexp_extract(c, r"(\d{1,3}(?:\.\d{1,3}){3})", 1))
        return c

    mapped = {f["asim"]: clean(f["asim"], field_col(base, f)) for f in group["fields"] if f.get("asim")}
    for c in group.get("constant_entities", []):
        if c.get("asim"):
            mapped[c["asim"]] = clean(c["asim"], field_col(base, c))
    mapped.update({"SourceTable": F.lit(group["table"]), "SourceGroup": F.lit(group["id"]),
                   "EventVendor": F.lit(group.get("vendor", "")), "EventProduct": F.lit(group.get("product", "")),
                   "EventSchema": F.lit(group.get("schema", "")), "EventType": event_type_col(base, group),
                   "EventResult": result_col(base, group, cfg["vocab"]), "MappingTier": F.lit(1)})
    cols = []
    for name, typ in cfg["event_columns"]:
        spark_type = {"string": "string", "int": "int", "datetime": "timestamp"}[typ]
        if name in ("EventStartTime", "SourceRecordKey"):
            cols.append(F.col(name))
        else:
            cols.append(mapped.get(name, F.lit(None)).cast(spark_type).alias(name))
    return base.select(*cols)


def load_base(provider, group: dict, start: datetime, end: datetime) -> DataFrame:
    tc = group.get("time_column", "TimeGenerated")
    df = provider.read_table(group["table"])
    df = df.where((F.col(tc) >= F.lit(start)) & (F.col(tc) < F.lit(end)))
    if group.get("spark_filter"):
        df = df.where(F.expr(group["spark_filter"]))
    return (df.withColumn("SourceRecordKey", F.expr(group["spark_record_key"]).cast("string"))
              .withColumn("EventStartTime", F.col(tc).cast("timestamp")))


def finish(df: DataFrame, columns: list) -> DataFrame:
    order = [c for c, _ in columns]
    return df.select(*order).withColumn("TimeGenerated", F.current_timestamp())


def run(spark, provider, cfg: dict, now: datetime | None = None) -> dict:
    spark.conf.set("spark.sql.session.timeZone", "UTC")
    now = now or datetime.now(timezone.utc)
    end = (now - DELAY).replace(minute=0, second=0, microsecond=0)
    start = end - WINDOW
    counts = {}
    for group in cfg["groups"]:
        if group.get("engine") != "notebook":
            continue
        base = load_base(provider, group, start, end).cache()
        ents = finish(entity_rows(base, group, cfg), cfg["entity_columns"])
        provider.save_as_table(ents, ENTITY_TABLE, write_options={"mode": "append"})
        counts[group["id"]] = ents.count()
        ev = event_rows(base, group, cfg)
        if ev is not None:
            provider.save_as_table(finish(ev, cfg["event_columns"]), EVENT_TABLE, write_options={"mode": "append"})
        base.unpersist()
    return counts


# %%
if __name__ == "__main__" and CONFIG_JSON != "{}":
    from sentinel_lake.providers import MicrosoftSentinelProvider
    provider = MicrosoftSentinelProvider(spark)  # noqa: F821  (spark is predefined in the notebook)
    print(run(spark, provider, json.loads(CONFIG_JSON)))  # noqa: F821
