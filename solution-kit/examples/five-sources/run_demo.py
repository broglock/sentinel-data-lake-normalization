"""Five log sources end to end, run locally.

1. Generates lake KQL for all five groups and writes it to ./kql/ (check it with
   tests/kql_check.js).
2. Runs the notebook engine (notebooks/02_index_longtail.py) over sample raw rows for all
   five sources, exactly as the lake notebook would: HuntEntity hourly rollup rows, _stats
   rows and HuntEvent rows. (In the lake the approved groups run as KQL jobs with the same
   output; the KQL is checked separately.)
3. Runs the hunt_value (HuntEntity) and auth_events (HuntEvent) MCP tool logic.
4. Writes everything to output.md.

Needs pyspark + Java:  python examples/five-sources/run_demo.py
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

import yaml
from pyspark.sql import SparkSession, functions as F

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(os.path.dirname(HERE))

# ---------------------------------------------------------------- 1. generate KQL (all approved, KQL jobs)
reg = yaml.safe_load(open(os.path.join(HERE, "five_sources.yaml")))
for g in reg["groups"]:
    g["status"] = "approved"
tmp = tempfile.mkdtemp()
for d in ("kql_out", "kql_out_reviewed"):
    shutil.rmtree(os.path.join(HERE, d), ignore_errors=True)
all_kql = os.path.join(tmp, "all_kql.yaml")
yaml.safe_dump(reg, open(all_kql, "w"), sort_keys=False)
subprocess.run([sys.executable, os.path.join(KIT, "generator", "generate.py"), "--registry", all_kql,
                "--vocab", os.path.join(KIT, "registry", "vocab.yaml"), "--out", os.path.join(HERE, "kql_out")],
               check=True)
cfg = json.load(open(os.path.join(HERE, "kql_out", "notebook", "notebook_config.json")))
for g in cfg["groups"]:
    g["engine"] = "notebook"          # run every group through the Spark engine for the demo

# ---------------------------------------------------------------- 2. sample raw rows
spark = (SparkSession.builder.master("local[1]").appName("five-sources")
         .config("spark.sql.session.timeZone", "UTC").getOrCreate())
spark.sparkContext.setLogLevel("ERROR")
t = lambda m, s: datetime(2026, 10, 18, 9, m, s, tzinfo=timezone.utc)
NOW = datetime(2026, 10, 18, 10, 30, tzinfo=timezone.utc)

tables = {
    "SecurityEvent": spark.createDataFrame([
        (t(14, 2), "DC01.corp.contoso.com", 4625, "jsmith", "203.0.113.45", "-", "0xc000006a"),
        (t(31, 40), "DC01.corp.contoso.com", 4624, "jsmith", "10.20.30.40", "WS-0412", "0x0"),
        (t(32, 5), "DC01.corp.contoso.com", 4624, "svc_backup", "-", "-", "0x0"),
    ], "TimeGenerated timestamp, Computer string, EventID int, TargetUserName string, IpAddress string, "
       "WorkstationName string, SubStatus string"),
    "CommonSecurityLog": spark.createDataFrame([
        (t(13, 55), "Fortinet", "Fortigate", "FGT-EDGE01", "203.0.113.45", "10.1.2.3", 51544, 3389, "", "deny", "TCP"),
        (t(31, 12), "Fortinet", "Fortigate", "FGT-EDGE01", "10.20.30.40", "198.51.100.7", 50211, 443, "jsmith", "accept", "TCP"),
    ], "TimeGenerated timestamp, DeviceVendor string, DeviceProduct string, DeviceName string, SourceIP string, "
       "DestinationIP string, SourcePort int, DestinationPort int, SourceUserName string, DeviceAction string, "
       "Protocol string"),
    "Syslog": spark.createDataFrame([
        (t(14, 30), "web-07", "sshd", "Failed password for invalid user admin from 203.0.113.45 port 52114 ssh2"),
        (t(14, 41), "web-07", "sshd", "Failed password for jsmith from 203.0.113.45 port 52130 ssh2"),
        (t(35, 0), "web-07", "sshd", "Accepted publickey for deploy from 10.20.30.40 port 40022 ssh2"),
    ], "TimeGenerated timestamp, Computer string, ProcessName string, SyslogMessage string"),
    "AppAudit_CL": spark.createDataFrame([
        (t(15, 3), json.dumps({"eventId": "a-1001", "operation": "Login", "outcome": "FAILED",
                               "client": {"addr": "203.0.113.45:8443"}, "actor": {"upn": "JSmith@contoso.com"},
                               "resource": {"url": "https://expenses.contoso.com/login"}})),
        (t(33, 9), json.dumps({"eventId": "a-1002", "operation": "Login", "outcome": "success",
                               "client": {"addr": "10.20.30.40"}, "actor": {"upn": "jsmith@contoso.com"},
                               "resource": {"url": "https://expenses.contoso.com/login"}})),
    ], "TimeGenerated timestamp, Properties string"),
    "VpnAppliance_CL": spark.createDataFrame([
        (t(15, 20), "vpn01 auth=fail user=jsmith src=203.0.113.45 tunnel=none reason=bad-otp"),
        (t(33, 50), "vpn01 auth=ok user=jsmith src=10.20.30.40 tunnel=ipsec-17"),
    ], "TimeGenerated timestamp, RawData string"),
}


class FakeProvider:
    """Stands in for MicrosoftSentinelProvider: read_table / save_as_table."""
    def __init__(self):
        self.saved = {}

    def read_table(self, name, database_name=None, database_id=None):
        return tables[name]

    def save_as_table(self, df, name, database_name=None, database_id=None, write_options=None):
        self.saved.setdefault(name, []).extend(r.asDict() for r in df.collect())


spec = importlib.util.spec_from_file_location("nb", os.path.join(KIT, "notebooks", "02_index_longtail.py"))
nb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nb)
p = FakeProvider()
counts = nb.run(spark, p, cfg, now=NOW)

saved = spark.createDataFrame(p.saved["HuntEntity_SPRK"])
ent = saved.where(F.col("EntityType") != "_stats")
ddl = ", ".join(f"{c} {dict(string='string', int='int', datetime='timestamp')[t]}" for c, t in cfg["event_columns"])
evt = spark.createDataFrame([{c: r.get(c) for c, _ in cfg["event_columns"]} for r in p.saved["HuntEvent_SPRK"]], ddl)


# ---------------------------------------------------------------- 3. MCP tool logic
def short(col):
    c = F.lower(F.trim(col))
    return F.when(c.contains("\\"), F.split(c, r"\\").getItem(1)).when(c.contains("@"), F.split(c, "@").getItem(0)).otherwise(c)


def hunt_value(value: str):
    v = value.strip().lower()
    vshort = v.split("\\")[1] if "\\" in v else (v.split("@")[0] if "@" in v else v)
    return (ent.where(F.col("ValueNorm").isin(v, vshort) | (F.lower("Value") == v))
               .groupBy("SourceTable", "SourceGroup", "EntityType")
               .agg(F.sum("Count").alias("Events"),
                    F.array_join(F.array_sort(F.collect_set("Role")), ", ").alias("Roles"),
                    F.array_join(F.array_sort(F.collect_set(F.col("MappingTier").cast("string"))), ", ").alias("Tiers"),
                    F.array_join(F.array_sort(F.collect_set("EventResult")), ", ").alias("Results"))
               .orderBy("SourceTable"))


def auth_events(user: str):
    """From HuntEvent: Tier 1 sign-in events with their result and source IP."""
    v = user.strip().lower()
    vshort = v.split("\\")[1] if "\\" in v else (v.split("@")[0] if "@" in v else v)
    u = F.when(F.col("TargetUsername") != "", F.col("TargetUsername")).otherwise(F.col("ActorUsername"))
    return (evt.where(F.col("EventType").isin("Logon", "Logoff") & (short(u) == vshort))
               .select(F.date_format("EventStartTime", "HH:mm:ss").alias("Time"), "SourceGroup", "EventType",
                       "EventResult", u.alias("User"), "SrcIpAddr")
               .orderBy("Time"))


def stats_md(df):
    st = df.where(F.col("EntityType") == "_stats").groupBy("SourceGroup").pivot("Role", list(cfg["stats_roles"])) \
           .agg(F.sum("Count")).orderBy("SourceGroup")
    return md(st)


def md(df, cols=None):
    rows = df.collect()
    cols = cols or df.columns
    out = ["| " + " | ".join(cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
    for r in rows:
        out.append("| " + " | ".join("" if r[c] is None else str(r[c]) for c in cols) + " |")
    return "\n".join(out)


# ---------------------------------------------------------------- 4. write output.md
parts = ["# Five sources: actual output of the demo run", "",
         f"Rows indexed per group: {counts}", ""]
ROLLUP_COLS = ["Hour", "EntityType", "Role", "Value", "ValueNorm", "ValueType", "EventType", "EventResult",
               "MappingLayer", "MappingTier", "Count", "FirstSeen"]


def rollup_md(df):
    return md(df.select(F.date_format("Hour", "HH:mm").alias("Hour"), *ROLLUP_COLS[1:-1],
                        F.date_format("FirstSeen", "HH:mm:ss").alias("FirstSeen"))
                .orderBy("EntityType", "Role", "ValueNorm", "EventResult"))


parts += ["HuntEntity is an hourly rollup: one row per hour, group, entity, role and result, with Count, "
          "FirstSeen, LastSeen and up to three sample record keys for the pivot to raw rows.", ""]
for g in cfg["groups"]:
    parts += [f"## {g['id']}", "", rollup_md(ent.where(F.col("SourceGroup") == g["id"])), ""]
parts += ["## _stats rows (what notebook 03 reads for coverage)", "", stats_md(saved), ""]
parts += ["## HuntEvent rows (Tier 1 field rules and Tier 1 templates)", "",
          md(evt.select(F.date_format("EventStartTime", "HH:mm:ss").alias("Time"), "SourceGroup", "EventType",
                        "EventResult", "SrcIpAddr", "DstIpAddr", "DstPortNumber", "TargetUsername", "SrcUsername",
                        "DvcHostname", "DvcAction").orderBy("Time")), ""]
parts += ["## hunt_value('203.0.113.45')", "", md(hunt_value("203.0.113.45")), ""]
parts += ["## auth_events('CONTOSO\\\\jsmith')", "", md(auth_events("CONTOSO\\jsmith")), ""]
# ---------------------------------------------------------------- 5. after review: VPN templates
# Notebook 01 mines two templates from VpnAppliance_CL; an analyst maps their slots.
vpn_templates = [
    {"id": "vpn-auth-fail", "match": "auth=fail",
     "regex": r"auth=fail user=(?P<TargetUsername>\S+) src=(?P<SrcIpAddr>\S+)",
     "event_type": "Logon", "event_result": "Failure", "tier": 1,
     "slots": {"TargetUsername": {"entity": "user", "role": "Target"}, "SrcIpAddr": {"entity": "ip", "role": "Src"}}},
    {"id": "vpn-auth-ok", "match": "auth=ok",
     "regex": r"auth=ok user=(?P<TargetUsername>\S+) src=(?P<SrcIpAddr>\S+)",
     "event_type": "Logon", "event_result": "Success", "tier": 1,
     "slots": {"TargetUsername": {"entity": "user", "role": "Target"}, "SrcIpAddr": {"entity": "ip", "role": "Src"}}},
]
for g in reg["groups"]:
    if g["id"] == "VpnAppliance_CL:raw":
        g["templates"] = vpn_templates
        g["schema"] = "Authentication"
        g["status"] = "approved"
yaml.safe_dump(reg, open(all_kql, "w"), sort_keys=False)
subprocess.run([sys.executable, os.path.join(KIT, "generator", "generate.py"), "--registry", all_kql,
                "--vocab", os.path.join(KIT, "registry", "vocab.yaml"), "--out", os.path.join(HERE, "kql_out_reviewed")],
               check=True)
cfg2 = json.load(open(os.path.join(HERE, "kql_out_reviewed", "notebook", "notebook_config.json")))
cfg2["groups"] = [dict(g, engine="notebook") for g in cfg2["groups"] if g["id"] == "VpnAppliance_CL:raw"]
p2 = FakeProvider()
nb.run(spark, p2, cfg2, now=NOW)
vpn_all = spark.createDataFrame(p2.saved["HuntEntity_SPRK"])
vpn = vpn_all.where(F.col("EntityType") != "_stats")
ent = ent.where(F.col("SourceGroup") != "VpnAppliance_CL:raw").unionByName(vpn)
evt = evt.unionByName(spark.createDataFrame(
    [{c: r.get(c) for c, _ in cfg["event_columns"]} for r in p2.saved.get("HuntEvent_SPRK", [])], ddl))
parts += ["# After review: VPN appliance templates approved", "",
          "## VpnAppliance_CL:raw (now Tier 1)", "", rollup_md(vpn), "",
          "## VpnAppliance_CL:raw _stats rows", "", stats_md(vpn_all), "",
          "## hunt_value('203.0.113.45') after review", "", md(hunt_value("203.0.113.45")), "",
          "## auth_events('CONTOSO\\\\jsmith') after review", "", md(auth_events("CONTOSO\\jsmith")), ""]
open(os.path.join(HERE, "output.md"), "w").write("\n".join(parts))
print("\n".join(parts))
