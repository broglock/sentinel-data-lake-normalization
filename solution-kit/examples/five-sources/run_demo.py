"""Five log sources end to end, run locally.

1. Generates lake KQL for all five groups and writes it to ./kql/ (check it with
   tests/kql_check.js).
2. Runs the long-tail notebook engine (notebooks/02_index_longtail.py) over sample raw
   rows for all five sources, exactly as the lake notebook would.
3. Runs the hunt_value and auth_events MCP tool logic over the resulting index.
4. Writes everything to output.md.

Needs pyspark + Java:  python examples/five-sources/run_demo.py
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

import yaml
from pyspark.sql import SparkSession, functions as F

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(os.path.dirname(HERE))

# ---------------------------------------------------------------- 1. generate KQL (all as KQL jobs)
reg = yaml.safe_load(open(os.path.join(HERE, "five_sources.yaml")))
for g in reg["groups"]:
    g["engine"] = "kql_job"
tmp = tempfile.mkdtemp()
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

ent = spark.createDataFrame(p.saved["HuntEntity_SPRK"])
ddl = ", ".join(f"{c} {dict(string='string', int='int', datetime='timestamp')[t]}" for c, t in cfg["event_columns"])
evt = spark.createDataFrame([{c: r.get(c) for c, _ in cfg["event_columns"]} for r in p.saved["HuntEvent_SPRK"]], ddl)

# ---------------------------------------------------------------- 3. MCP tool logic
def hunt_value(value: str):
    v = value.strip().lower()
    vshort = v.split("\\")[1] if "\\" in v else (v.split("@")[0] if "@" in v else v)
    return (ent.where(F.col("ValueNorm").isin(v, vshort) | (F.lower("Value") == v))
               .groupBy("SourceTable", "SourceGroup", "EntityType")
               .agg(F.count("*").alias("Events"),
                    F.array_join(F.array_sort(F.collect_set("Role")), ", ").alias("Roles"),
                    F.array_join(F.array_sort(F.collect_set(F.col("MappingTier").cast("string"))), ", ").alias("Tiers"),
                    F.array_join(F.array_sort(F.collect_set("EventResult")), ", ").alias("Results"))
               .orderBy("SourceTable"))


def auth_events(user: str):
    v = user.strip().lower()
    vshort = v.split("\\")[1] if "\\" in v else (v.split("@")[0] if "@" in v else v)
    users = ent.where((F.col("EntityType") == "user") & (F.col("ValueNorm") == vshort) &
                      (F.col("MappingTier") == 1) & (F.col("EventType").isin("Logon", "Logoff")))
    src = ent.where((F.col("EntityType") == "ip") & (F.col("Role") == "Src")) \
             .select("SourceRecordKey", F.col("ValueNorm").alias("SrcIpAddr"))
    return (users.join(src, "SourceRecordKey", "left")
                 .select(F.date_format("EventStartTime", "HH:mm:ss").alias("Time"), "SourceGroup", "EventType",
                         "EventResult", F.col("Value").alias("User"), "SrcIpAddr")
                 .orderBy("Time"))


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
for g in cfg["groups"]:
    parts += [f"## {g['id']}", "",
              md(ent.where(F.col("SourceGroup") == g["id"])
                    .select(F.date_format("EventStartTime", "HH:mm:ss").alias("Time"), "EntityType", "Role",
                            "Value", "ValueNorm", "ValueType", "EventType", "EventResult", "MappingLayer",
                            "MappingTier").orderBy("Time", "EntityType")), ""]
parts += ["## HuntEvent rows (Tier 1, structured sources)", "",
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
yaml.safe_dump(reg, open(all_kql, "w"), sort_keys=False)
subprocess.run([sys.executable, os.path.join(KIT, "generator", "generate.py"), "--registry", all_kql,
                "--vocab", os.path.join(KIT, "registry", "vocab.yaml"), "--out", os.path.join(HERE, "kql_out_reviewed")],
               check=True)
cfg2 = json.load(open(os.path.join(HERE, "kql_out_reviewed", "notebook", "notebook_config.json")))
cfg2["groups"] = [dict(g, engine="notebook") for g in cfg2["groups"] if g["id"] == "VpnAppliance_CL:raw"]
p2 = FakeProvider()
nb.run(spark, p2, cfg2, now=NOW)
vpn = spark.createDataFrame(p2.saved["HuntEntity_SPRK"])
ent = ent.where(F.col("SourceGroup") != "VpnAppliance_CL:raw").unionByName(vpn)
parts += ["# After review: VPN appliance templates approved", "",
          "## VpnAppliance_CL:raw (now Tier 1)", "",
          md(vpn.select(F.date_format("EventStartTime", "HH:mm:ss").alias("Time"), "EntityType", "Role", "Value",
                        "ValueNorm", "ValueType", "EventType", "EventResult", "MappingLayer", "MappingTier")
                .orderBy("Time", "EntityType")), "",
          "## hunt_value('203.0.113.45') after review", "", md(hunt_value("203.0.113.45")), "",
          "## auth_events('CONTOSO\\\\jsmith') after review", "", md(auth_events("CONTOSO\\jsmith")), ""]
open(os.path.join(HERE, "output.md"), "w").write("\n".join(parts))
print("\n".join(parts))
