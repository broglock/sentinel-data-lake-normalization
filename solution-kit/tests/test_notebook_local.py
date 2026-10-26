"""Local test of notebooks/02_index_longtail.py with a fake Sentinel provider.

Runs the long-tail indexer on sample rows for every example group (engine forced to
notebook) and checks the entity rows it produces. Needs pyspark and Java:
  python tests/test_notebook_local.py
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

from pyspark.sql import SparkSession, functions as F

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)

# Build the notebook config with the generator.
out = tempfile.mkdtemp()
subprocess.run([sys.executable, os.path.join(KIT, "generator", "generate.py"),
                "--registry", os.path.join(KIT, "registry", "groups.example.yaml"),
                "--vocab", os.path.join(KIT, "registry", "vocab.yaml"), "--out", out], check=True)
cfg = json.load(open(os.path.join(out, "notebook", "notebook_config.json")))
for g in cfg["groups"]:
    g["engine"] = "notebook"

spec = importlib.util.spec_from_file_location("nb", os.path.join(KIT, "notebooks", "02_index_longtail.py"))
nb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nb)

spark = (SparkSession.builder.master("local[1]").appName("kit-test")
         .config("spark.sql.session.timeZone", "UTC").getOrCreate())
spark.sparkContext.setLogLevel("ERROR")
T = datetime(2026, 10, 18, 9, 20, tzinfo=timezone.utc)
NOW = datetime(2026, 10, 18, 10, 30, tzinfo=timezone.utc)   # window = 09:00 to 10:00

tables = {
    "Syslog": spark.createDataFrame([
        (T, "web-07", "10.0.0.7", "sshd", "Failed password for invalid user admin from 203.0.113.45 port 52114 ssh2"),
        (T, "web-07", "10.0.0.7", "sshd", "Accepted publickey for deploy from 198.51.100.20 port 40022 ssh2: RSA SHA256:abc"),
        (T, "web-07", "10.0.0.7", "sshd", "Connection closed by 192.0.2.9 port 22 [preauth] version v10.2.0.1"),
        (T, "web-07", "10.0.0.7", "cron", "ignored by filter 192.0.2.200"),
    ], "TimeGenerated timestamp, Computer string, HostIP string, ProcessName string, SyslogMessage string"),
    "CommonSecurityLog": spark.createDataFrame([
        (T, "Palo Alto Networks", "PAN-OS", "FW01.corp.contoso.com", "Oct 18 2026", "203.0.113.45", "10.1.2.3",
         51000, 443, "CONTOSO\\jsmith", "", "hxxps://evil[.]example/x", "deny", "tcp", "untrust", "Destination Zone"),
    ], "TimeGenerated timestamp, DeviceVendor string, DeviceProduct string, DeviceName string, ReceiptTime string, "
       "SourceIP string, DestinationIP string, SourcePort int, DestinationPort int, SourceUserName string, "
       "DestinationUserName string, RequestURL string, DeviceAction string, Protocol string, "
       "DeviceCustomString2 string, DeviceCustomString2Label string"),
    "AppAudit_CL": spark.createDataFrame([
        (T, json.dumps({"eventId": "e-1", "operation": "Login", "outcome": "FAILED",
                        "client": {"addr": "203.0.113.45:8443"}, "actor": {"upn": "JSmith@Contoso.com"},
                        "target": {"account": "-"}, "resource": {"url": "https://app.contoso.com/a"}})),
    ], "TimeGenerated timestamp, Properties string"),
    "Appliance_CL": spark.createDataFrame([
        (T, "appl01 login fail user=bob src=203.0.113.45 hash=" + "a" * 64 + " see http://x.example/p"),
    ], "TimeGenerated timestamp, RawData string"),
}


class FakeProvider:
    def __init__(self):
        self.saved = {}

    def read_table(self, name, database_name=None, database_id=None):
        return tables[name]

    def save_as_table(self, df, name, database_name=None, database_id=None, write_options=None):
        self.saved.setdefault(name, []).extend(r.asDict() for r in df.collect())


p = FakeProvider()
counts = nb.run(spark, p, cfg, now=NOW)
print("rows per group:", counts)
ents = p.saved["HuntEntity_SPRK"]
for r in sorted(ents, key=lambda r: (r["SourceGroup"], r["EntityType"], r["ValueNorm"])):
    print(f'{r["SourceGroup"]:<32} {r["EntityType"]:<6} {r["Role"]:<7} {r["ValueNorm"]:<26} '
          f'{r["ValueType"]:<8} {r["MappingLayer"]:<10} T{r["MappingTier"]} {r["EventType"] or "-"}/{r["EventResult"] or "-"}')


def has(group, etype, norm, role=None, tier=None):
    for r in ents:
        if r["SourceGroup"] == group and r["EntityType"] == etype and r["ValueNorm"] == norm \
                and (role is None or r["Role"] == role) and (tier is None or r["MappingTier"] == tier):
            return True
    return False


checks = [
    has("Syslog:sshd", "user", "admin", "Target", 1),
    has("Syslog:sshd", "ip", "203.0.113.45", "Src", 1),
    has("Syslog:sshd", "ip", "192.0.2.9", "Unknown", 2),          # unmatched line, classifier
    not has("Syslog:sshd", "ip", "10.2.0.1"),                     # version string rejected
    not has("Syslog:sshd", "ip", "192.0.2.200"),                  # filtered out (cron)
    has("CEF:Palo Alto Networks/PAN-OS", "user", "jsmith", "Src", 1),
    has("CEF:Palo Alto Networks/PAN-OS", "host", "fw01", "Dvc", 1),
    has("CEF:Palo Alto Networks/PAN-OS", "url", "https://evil.example/x"),
    has("AppAudit_CL:v2", "ip", "203.0.113.45", "Src", 2),        # port stripped
    has("AppAudit_CL:v2", "user", "jsmith", "Actor", 2),
    not has("AppAudit_CL:v2", "user", "-"),                       # null value dropped
    has("Appliance_CL:raw", "hash", "a" * 64, "Unknown", 2),
    has("Appliance_CL:raw", "ip", "203.0.113.45", "Unknown", 2),
]
events = p.saved.get("HuntEvent_SPRK", [])
pan = [e for e in events if e["SourceGroup"] == "CEF:Palo Alto Networks/PAN-OS"]
checks.append(len(pan) == 1 and pan[0]["EventResult"] == "Failure" and pan[0]["DstZone"] == "untrust")
aud = [r for r in ents if r["SourceGroup"] == "AppAudit_CL:v2"]
checks.append(all(r["EventResult"] == "Failure" for r in aud))
print("checks:", checks)
assert all(checks), "a check failed"
print("ALL CHECKS PASSED")

# ---------------------------------------------------------------- notebooks 01 and 03
spec1 = importlib.util.spec_from_file_location("nb1", os.path.join(KIT, "notebooks", "01_inventory_and_mining.py"))
nb1 = importlib.util.module_from_spec(spec1); spec1.loader.exec_module(nb1)
spec3 = importlib.util.spec_from_file_location("nb3", os.path.join(KIT, "notebooks", "03_coverage.py"))
nb3 = importlib.util.module_from_spec(spec3); spec3.loader.exec_module(nb3)

tables["HuntEntity_SPRK"] = spark.createDataFrame(
    [{**r, "TimeGenerated": NOW} for r in ents]).select(*[c for c, _ in cfg["entity_columns"]], "TimeGenerated")


class FakeProvider2(FakeProvider):
    def list_tables(self, database_name=None, database_id=None):
        return ["Syslog", "CommonSecurityLog", "AppAudit_CL", "Appliance_CL", "HuntEntity_SPRK"]

    def read_table(self, name, database_name=None, database_id=None):
        if name not in tables:
            raise ValueError("no such table")
        return tables[name]


p2 = FakeProvider2()
inv_df, mined = nb1.run(spark, p2, cfg["vocab"], now=NOW)
inv = {(r["TableName"], r["FieldPath"]): r for r in inv_df.collect()}
print("inventory rows:", len(inv))
for k in [("AppAudit_CL", "Properties.client.addr"), ("AppAudit_CL", "Properties.actor.upn"),
          ("CommonSecurityLog", "SourceIP"), ("Appliance_CL", "RawData.src")]:
    r = inv.get(k)
    print(k, r and (r["TopValueClass"], r["ProposedAsim"], r["ProposedRole"], r["ProposedEntity"]))
assert inv[("AppAudit_CL", "Properties.client.addr")]["ProposedEntity"] == "ip"
assert inv[("CommonSecurityLog", "SourceIP")]["ProposedAsim"] == "SrcIpAddr"
assert inv[("AppAudit_CL", "Properties.actor.upn")]["ProposedEntity"] == "user"
for r in mined.orderBy("TableName", "GroupKey", F.desc("Lines")).collect():
    print("template:", r["TableName"], r["GroupKey"], r["Lines"], r["Template"][:90])
assert any("Failed password for invalid user admin from <IP> port <NUM> ssh2" == r["Template"] for r in mined.collect())

cov = nb3.run(spark, p2, cfg, now=NOW + __import__("datetime").timedelta(hours=1))
for r in cov:
    print("coverage:", r["SourceGroup"], "tier", r["Tier"], "raw", r["RawRows"], "indexed", r["IndexedRows"],
          "extraction", r["ExtractionRate"], "templates", r["TemplateMatchRate"], "|", r["Status"])
assert all(r["ExtractionRate"] == 1.0 for r in cov)
print("NOTEBOOK 01 AND 03 CHECKS PASSED")
