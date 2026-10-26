"""Parity check: the in-app Python engine and the lake notebook (Spark) produce the same index.

Runs every notebook-capable demo group through both engines on the same demo rows and compares
the entity rows (SourceGroup, SourceRecordKey, EntityType, Role, ValueNorm, MappingTier, EventResult).
Needs pyspark and Java:  python tests/parity_spark.py
"""
from __future__ import annotations

import importlib.util
import sys
from collections import Counter
from datetime import timedelta
from pathlib import Path

import yaml
from pyspark.sql import SparkSession
from pyspark.sql.types import IntegerType, StringType, StructField, StructType, TimestampType

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.demo.demo_data import anchor_now, build  # noqa: E402
from app.engine.indexer import index_group  # noqa: E402
from app.kit.generate import notebook_config  # noqa: E402

spec = importlib.util.spec_from_file_location("nb", ROOT / "app" / "kit" / "notebooks" / "02_index_longtail.py")
nb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nb)


def spark_type(v):
    if isinstance(v, bool):
        return StringType()
    if isinstance(v, int):
        return IntegerType()
    if hasattr(v, "tzinfo"):
        return TimestampType()
    return StringType()


def main() -> int:
    spark = (SparkSession.builder.master("local[1]").appName("parity")
             .config("spark.sql.session.timeZone", "UTC").getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")
    now = anchor_now()
    raw = build(now)
    reg = yaml.safe_load(open(ROOT / "app" / "demo" / "demo_registry.yaml"))
    vocab = yaml.safe_load(open(ROOT / "app" / "kit" / "vocab.yaml"))
    cfg = notebook_config(reg["groups"], vocab)
    frames = {}
    for t, rows in raw.items():
        cols = list(rows[0].keys())
        schema = StructType([StructField(c, spark_type(rows[0][c]), True) for c in cols])
        frames[t] = spark.createDataFrame([tuple(r.get(c) for c in cols) for r in rows], schema)

    class P:
        def __init__(self):
            self.saved = {}

        def read_table(self, name, **_):
            return frames[name]

        def save_as_table(self, df, name, **_):
            self.saved.setdefault(name, []).extend(r.asDict() for r in df.collect())

    nb.WINDOW = timedelta(days=8)          # index the whole demo week in one run
    nb.DELAY = timedelta(0)
    p = P()
    for g in cfg["groups"]:
        g["engine"] = "notebook"
    nb.run(spark, p, cfg, now=now + timedelta(hours=1))
    key = lambda e: (e["SourceGroup"], e["SourceRecordKey"], e["EntityType"], e["Role"], e["ValueNorm"],  # noqa: E731
                     int(e["MappingTier"]), e["EventResult"] or "")
    spark_rows = Counter(key(e) for e in p.saved.get("HuntEntity_SPRK", []))
    py_rows = Counter()
    end = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    start = end - nb.WINDOW
    for g in reg["groups"]:
        rows = [r for r in raw[g["table"]] if start <= r["TimeGenerated"] < end]
        ents, _ = index_group(rows, g, vocab)
        py_rows.update(key(e) for e in ents)
    only_spark, only_py = spark_rows - py_rows, py_rows - spark_rows
    print(f"spark entity rows {sum(spark_rows.values())}, python entity rows {sum(py_rows.values())}")
    for name, diff in (("only in Spark", only_spark), ("only in Python", only_py)):
        if diff:
            print(name, sum(diff.values()))
            for k in list(diff)[:10]:
                print("  ", k)
    by_group = Counter(k[0] for k in spark_rows.elements())
    print("per group:", dict(by_group))
    spark.stop()
    return 0 if not only_spark and not only_py else 1


if __name__ == "__main__":
    raise SystemExit(main())
