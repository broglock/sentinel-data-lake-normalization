"""Parity check: the in-app Python engine and the lake notebook (Spark) produce the same index.

Runs every demo group through both engines on the same demo rows and compares the HuntEntity rows
(hourly rollup and _stats rows, every column including Count, FirstSeen, LastSeen and SampleKeys)
and the HuntEvent rows.
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
from app.kit.generate import ENTITY_COLUMNS, EVENT_COLUMNS  # noqa: E402
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
    def norm(v):
        if hasattr(v, "strftime"):
            return v.replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M:%S.%f")
        if isinstance(v, (list, tuple)):
            return tuple(v)
        return "" if v is None else v

    ent_key = lambda e: tuple(norm(e.get(c)) for c, _ in ENTITY_COLUMNS)  # noqa: E731
    ev_key = lambda e: tuple(norm(e.get(c)) for c, _ in EVENT_COLUMNS)  # noqa: E731
    spark_rows = Counter(ent_key(e) for e in p.saved.get("HuntEntity_SPRK", []))
    spark_ev = Counter(ev_key(e) for e in p.saved.get("HuntEvent_SPRK", []))
    py_rows, py_ev = Counter(), Counter()
    end = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    start = end - nb.WINDOW
    for g in reg["groups"]:
        rows = [r for r in raw[g["table"]] if start <= r["TimeGenerated"] < end]
        ents, evs = index_group(rows, g, vocab)
        py_rows.update(ent_key(e) for e in ents)
        py_ev.update(ev_key(e) for e in evs)
    print(f"HuntEntity: spark {sum(spark_rows.values())} rows, python {sum(py_rows.values())} rows")
    print(f"HuntEvent:  spark {sum(spark_ev.values())} rows, python {sum(py_ev.values())} rows")
    bad = False
    for table, a, b in (("HuntEntity", spark_rows, py_rows), ("HuntEvent", spark_ev, py_ev)):
        for name, diff in (("only in Spark", a - b), ("only in Python", b - a)):
            if diff:
                bad = True
                print(table, name, sum(diff.values()))
                for k in list(diff)[:5]:
                    print("  ", k)
    by_group = Counter(k[4] for k in spark_rows.elements())
    print("per group:", dict(by_group))
    spark.stop()
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
