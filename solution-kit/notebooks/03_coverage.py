# %% [markdown]
# # 03 Coverage report
# Daily notebook job. One row per registry group in HuntCoverage_SPRK: tier, raw rows,
# indexed rows, extraction rate, template match rate, unknown-role share, last index
# write, and a status that compares today with the group's own trailing 28 days.
# The MCP `coverage` tool reads this table.
#
# It reads no source tables. Every index job (KQL job or notebook 02) writes "_stats" rows
# into HuntEntity with the rows it read, the rows that produced an entity and the rows a
# template matched; this notebook sums those and reads the rollup rows for role shares.

# %%
import json
from datetime import datetime, timedelta, timezone

from pyspark.sql import functions as F

CONFIG_JSON = "{}"           # paste notebook_config.json here
LOOKBACK = timedelta(days=1)
ENTITY_TABLES = ["HuntEntity_SPRK", "HuntEntity_KQL"]   # notebook output and KQL job output
COVERAGE_TABLE = "HuntCoverage_SPRK"
THRESHOLDS = {"extraction_structured": 0.90, "template_match": 0.70, "unknown_role": 0.30,
              "drop_points": 0.20, "stale_hours": 2}


# %%
def group_tier(g: dict) -> int:
    tiers = [int(g.get("tier", 2))] + [int(t.get("tier", 2)) for t in g.get("templates", []) or []]
    return min(tiers) if tiers else 3


def read_index(provider, start: datetime, end: datetime):
    """The last day of HuntEntity rows from every index table that exists."""
    out = None
    for t in ENTITY_TABLES:
        try:
            df = provider.read_table(t)
        except Exception:  # table not created yet (no KQL jobs or no notebook groups)
            continue
        df = df.where((F.col("Hour") >= F.lit(start)) & (F.col("Hour") < F.lit(end)))
        out = df if out is None else out.unionByName(df, allowMissingColumns=True)
    return out


def measure(g: dict, idx) -> dict:
    e = idx.where(F.col("SourceGroup") == g["id"]) if idx is not None else None
    sums = {}
    if e is not None:
        for r in e.where(F.col("EntityType") == "_stats").groupBy("Role").agg(F.sum("Count").alias("n")).collect():
            sums[r["Role"]] = int(r["n"] or 0)
        ent = e.where(F.col("EntityType") != "_stats")
        agg = ent.agg(F.sum("Count").alias("all"),
                      F.sum(F.when(F.col("Role") == "Unknown", F.col("Count")).otherwise(0)).alias("unknown"),
                      F.max("LastSeen").alias("last")).first()
    else:
        agg = {"all": 0, "unknown": 0, "last": None}
    raw_rows, indexed = sums.get("RowsRead", 0), sums.get("RowsWithEntity", 0)
    templ = sums.get("RowsTemplateMatched", 0)
    text = bool(g.get("text_column"))
    ent_rows = int(agg["all"] or 0)
    return {
        "SourceGroup": g["id"], "SourceTable": g["table"], "Engine": g.get("engine", "notebook"),
        "Tier": group_tier(g), "RawRows": raw_rows, "IndexedRows": indexed,
        "ExtractionRate": round(indexed / raw_rows, 4) if raw_rows else None,
        "TemplateMatchRate": round(templ / raw_rows, 4) if (raw_rows and text and g.get("templates")) else None,
        "UnknownRoleShare": round(int(agg["unknown"] or 0) / ent_rows, 4) if ent_rows else None,
        "LastIndexed": agg["last"], "HasText": text,
    }


def status(row: dict, history: dict, now: datetime) -> str:
    flags = []
    er, tm, ur = row["ExtractionRate"], row["TemplateMatchRate"], row["UnknownRoleShare"]
    if row["RawRows"] and not row["IndexedRows"]:
        flags.append("raw rows but nothing indexed: job rejected, failed or filter mismatch")
    if er is not None and not row["HasText"] and er < THRESHOLDS["extraction_structured"]:
        flags.append("low extraction")
    avg = history.get(row["SourceGroup"])
    if er is not None and avg is not None and avg - er > THRESHOLDS["drop_points"]:
        flags.append("extraction dropped vs 28-day average")
    if tm is not None and tm < THRESHOLDS["template_match"]:
        flags.append("mine more templates")
    if ur is not None and row["Tier"] == 1 and ur > THRESHOLDS["unknown_role"]:
        flags.append("review role rules")
    return "; ".join(flags) or "ok"


def run(spark, provider, cfg: dict, now: datetime | None = None):
    spark.conf.set("spark.sql.session.timeZone", "UTC")
    now = now or datetime.now(timezone.utc)
    end = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    start = end - LOOKBACK
    idx = read_index(provider, start, end)
    if idx is not None:
        idx = idx.cache()
    try:
        hist = provider.read_table(COVERAGE_TABLE).where(F.col("TimeGenerated") >= F.lit(now - timedelta(days=28)))
        history = {r["SourceGroup"]: r["avg"] for r in
                   hist.groupBy("SourceGroup").agg(F.avg("ExtractionRate").alias("avg")).collect()}
    except Exception:  # first run: no history table yet
        history = {}
    rows = []
    for g in cfg["groups"]:
        r = measure(g, idx)
        r["Status"] = status(r, history, now)
        rows.append(r)
    df = spark.createDataFrame(rows).withColumn("TimeGenerated", F.current_timestamp())
    provider.save_as_table(df, COVERAGE_TABLE, write_options={"mode": "append"})
    if idx is not None:
        idx.unpersist()
    return rows


# %%
if __name__ == "__main__" and CONFIG_JSON != "{}":
    from sentinel_lake.providers import MicrosoftSentinelProvider
    provider = MicrosoftSentinelProvider(spark)  # noqa: F821
    for r in run(spark, provider, json.loads(CONFIG_JSON)):  # noqa: F821
        print(r["SourceGroup"], r["Tier"], r["ExtractionRate"], r["Status"])
