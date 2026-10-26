"""Build the connector catalog snapshot from a checkout of github.com/Azure/Azure-Sentinel.

For every solution: name, version, author, data connectors, the tables each connector
writes, table schemas where the repo defines them (custom/CCF tables and DCR streams),
and which ASIM parsers read those tables.

Usage: python tools/build_catalog.py <Azure-Sentinel checkout> app/data/catalog.json
Sparse checkout that is enough:
  git clone --depth 1 --filter=blob:none --sparse https://github.com/Azure/Azure-Sentinel.git
  git sparse-checkout set --no-cone '/Solutions/*/Data/*.json' '/Solutions/*/Data Connectors/**/*.json' '/Parsers/ASim*/Parsers/*.yaml'
"""
import glob
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

import yaml

ROOT, OUT = sys.argv[1], sys.argv[2]
TABLE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{1,62}$")


def load(path):
    for enc in ("utf-8-sig", "utf-16"):
        try:
            with open(path, encoding=enc) as f:
                return json.load(f)
        except Exception:
            continue
    return None


def walk(o):
    """Yield every dict inside a JSON value."""
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk(v)


def clean_type(t):
    t = (t or "string").lower()
    return {"int": "int", "long": "long", "real": "real", "double": "real", "bool": "bool", "boolean": "bool",
            "datetime": "datetime", "dynamic": "dynamic", "guid": "guid", "string": "string"}.get(t, "string")


solutions = []
all_schemas = {}
for sdir in sorted(glob.glob(os.path.join(ROOT, "Solutions", "*"))):
    if not os.path.isdir(sdir):
        continue
    meta = {}
    for f in glob.glob(os.path.join(sdir, "Data", "Solution_*.json")):
        d = load(f)
        if isinstance(d, dict) and d.get("Name"):
            meta = d
            break
    connectors, tables = [], set()
    for f in glob.glob(os.path.join(sdir, "Data Connectors", "**", "*.json"), recursive=True):
        d = load(f)
        if d is None:
            continue
        for node in walk(d):
            # classic and CCF connector UI definitions
            ui = node.get("connectorUiConfig") if isinstance(node.get("connectorUiConfig"), dict) else node
            if isinstance(ui.get("dataTypes"), list) and ui.get("title"):
                names = []
                for dt in ui["dataTypes"]:
                    n = str(dt.get("name", "")).strip()
                    n = re.split(r"[\s(|]", n)[0] if n else ""
                    if n.startswith("{{") or not TABLE_RE.match(n or "x!"):
                        continue
                    names.append(n)
                if names:
                    title = re.sub(r"\s+", " ", str(ui["title"])).strip()
                    if title not in {c["title"] for c in connectors}:
                        connectors.append({"title": title, "publisher": ui.get("publisher", ""),
                                           "id": str(ui.get("id", "")), "tables": sorted(set(names)),
                                           "kind": "CCF" if node is not ui else "classic",
                                           "deprecated": "[deprecated]" in title.lower()})
                    tables.update(names)
            # table definitions with schemas
            props = node.get("properties") if isinstance(node.get("properties"), dict) else {}
            sch = props.get("schema") if isinstance(props.get("schema"), dict) else None
            if str(node.get("type", "")).endswith("workspaces/tables") and sch and sch.get("columns"):
                n = sch.get("name") or str(node.get("name", "")).split("/")[-1]
                if TABLE_RE.match(n or "x!"):
                    all_schemas[n] = [{"name": c["name"], "type": clean_type(c.get("type"))}
                                      for c in sch["columns"] if c.get("name")]
                    tables.add(n)
            # DCR stream declarations: Custom-<Table>_CL
            sd = props.get("streamDeclarations")
            if isinstance(sd, dict):
                for sname, sval in sd.items():
                    m = re.match(r"Custom-(.+)$", sname)
                    if m and isinstance(sval, dict) and sval.get("columns"):
                        n = m.group(1)
                        if n.endswith("_CL") and TABLE_RE.match(n) and n not in all_schemas:
                            all_schemas[n] = [{"name": c["name"], "type": clean_type(c.get("type"))}
                                              for c in sval["columns"] if c.get("name")]
    if not connectors and not meta:
        continue
    solutions.append({
        "name": meta.get("Name") or os.path.basename(sdir),
        "folder": os.path.basename(sdir),
        "version": str(meta.get("Version", "")),
        "author": str(meta.get("Author", "")).split(" - ")[0],
        "dependsOn": meta.get("dependentDomainSolutionIds", []),
        "connectors": connectors,
        "tables": sorted(tables),
    })

# ASIM parsers and the tables they read
known_tables = set(all_schemas)
for s in solutions:
    known_tables.update(s["tables"])
known_tables.update(["SecurityEvent", "WindowsEvent", "Syslog", "CommonSecurityLog", "SigninLogs",
                     "AADNonInteractiveUserSignInLogs", "AWSCloudTrail", "AzureActivity", "AzureDiagnostics",
                     "DeviceProcessEvents", "DeviceNetworkEvents", "DeviceFileEvents", "DeviceLogonEvents",
                     "Event", "OfficeActivity", "AuditLogs", "DnsEvents", "W3CIISLog", "VMConnection",
                     "AzureFirewallNetworkRule", "AzureFirewallApplicationRule", "NTANetAnalytics"])
parsers = []
for f in sorted(glob.glob(os.path.join(ROOT, "Parsers", "ASim*", "Parsers", "*.yaml"))):
    try:
        y = yaml.safe_load(open(f, encoding="utf-8-sig"))
    except Exception:
        continue
    if not isinstance(y, dict) or not y.get("ParserQuery"):
        continue
    name = y.get("ParserName", "")
    if name.lower().startswith(("asim", "vim")) and name in ("ASim" + y.get("Normalization", {}).get("Schema", ""),):
        continue  # unifying parser
    q = y["ParserQuery"]
    tabs = sorted({t for t in re.findall(r"\b([A-Za-z][A-Za-z0-9_]+)\b", q) if t in known_tables})
    if not tabs:
        continue
    parsers.append({"parser": name, "builtIn": y.get("EquivalentBuiltInParser", ""),
                    "schema": y.get("Normalization", {}).get("Schema", ""),
                    "product": (y.get("Product") or {}).get("Name", ""), "tables": tabs})

by_table = {}
for p in parsers:
    for t in p["tables"]:
        by_table.setdefault(t, []).append(p["builtIn"] or p["parser"])
for s in solutions:
    s["asimTables"] = sorted(t for t in s["tables"] if t in by_table)

try:
    commit = subprocess.check_output(["git", "-C", ROOT, "rev-parse", "--short", "HEAD"], text=True).strip()
except Exception:
    commit = ""
out = {"source": "https://github.com/Azure/Azure-Sentinel", "commit": commit,
       "built": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
       "solutions": solutions, "parsers": parsers, "schemas": all_schemas}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump(out, open(OUT, "w"), separators=(",", ":"))
n_conn = sum(len(s["connectors"]) for s in solutions)
n_tab = len({t for s in solutions for t in s["tables"]})
print(f"solutions={len(solutions)} connectors={n_conn} tables={n_tab} schemas={len(all_schemas)} "
      f"asim_parsers={len(parsers)} asim_tables={len(by_table)}")
