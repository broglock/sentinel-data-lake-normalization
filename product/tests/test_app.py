"""End-to-end tests in demo mode: engine, REST workflow, MCP, generated KQL.
Run from the product folder:  python -m pytest -q tests
The KQL test needs Node.js and @kusto/language-service-next (KUSTO_LIB=<node_modules dir>); it skips otherwise.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

os.environ["LAKEHUNT_DATA_DIR"] = tempfile.mkdtemp(prefix="lakehunt-test-")
os.environ.setdefault("LAKEHUNT_MODE", "demo")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

ATTACKER = "203.0.113.45"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def ok(r):
    assert r.status_code == 200, r.text[:600]
    return r.json()


# ------------------------------------------------------------------ engine
def test_normalize_rules():
    from app.engine.indexer import normalize
    nulls = ["", "-", "n/a"]
    assert normalize("ip", "203.0.113.45:8443", nulls) == ("203.0.113.45:8443", "IPv4", "203.0.113.45")
    assert normalize("user", "CONTOSO\\JSmith", nulls)[2] == "jsmith"
    assert normalize("user", "JSmith@contoso.com", nulls)[1:] == ("UPN", "jsmith")
    assert normalize("host", "DC01.corp.contoso.com", nulls)[2] == "dc01"
    assert normalize("ip", "999.1.1.1", nulls) is None
    assert normalize("host", "10.1.2.3", nulls) is None
    assert normalize("user", "-", nulls) is None


def test_record_key_matches_kql_definition():
    import hashlib
    from datetime import datetime, timezone
    from app.engine.indexer import record_key
    g = {"id": "x", "table": "T", "record_key_fields": ["A", "B"]}
    row = {"TimeGenerated": datetime(2026, 10, 18, 9, 14, 2, 123456, tzinfo=timezone.utc), "A": "a", "B": None}
    assert record_key(row, g) == hashlib.sha256(b"2026-10-18 09:14:02.123|a|").hexdigest()


# ------------------------------------------------------------------ dashboards and hunting
def test_overview_and_coverage(client):
    o = ok(client.get("/api/v1/overview"))
    assert o["tables"] >= 9 and o["tier1"] >= 8
    cov = {c["SourceGroup"]: c for c in o["coverage"]}
    assert cov["SecurityEvent:Logon"]["Status"] == "ok"
    assert cov["VpnAppliance_CL:raw"]["Status"] == "review"      # keepalive lines carry no entities
    assert cov["BadgeReader_CL:auto"]["Status"] == "classifier-only"


def test_hunt_value_finds_attacker_in_every_auth_source(client):
    r = ok(client.get("/api/v1/hunt/value", params={"v": ATTACKER, "days": 7}))
    groups = {s["SourceGroup"] for s in r["sources"]}
    for g in ["SecurityEvent:Logon", "SigninLogs:Interactive", "CEF:Fortinet/Fortigate", "CEF:PaloAlto/PAN-OS",
              "Syslog:sshd", "AWSCloudTrail:ConsoleLogin", "OktaV2_CL:session", "AppAudit_CL:v2", "VpnAppliance_CL:raw"]:
        assert g in groups, g
    assert all("Src" in s["Roles"] for s in r["sources"])
    assert any(x["Value"] == "jsmith" for x in r["related"])


def test_user_formats_resolve_to_one_identity(client):
    a = ok(client.get("/api/v1/hunt/auth", params={"user": "CONTOSO\\jsmith", "days": 7}))
    b = ok(client.get("/api/v1/hunt/auth", params={"user": "jsmith@contoso.com", "days": 7}))
    assert len(a) == len(b) > 5
    assert any(x["SrcIpAddr"] == ATTACKER and x["EventResult"] == "Success" for x in a)


def test_pivot_returns_the_raw_row(client):
    t = ok(client.get("/api/v1/hunt/value", params={"v": ATTACKER}))["timeline"][0]
    rows = ok(client.get("/api/v1/hunt/pivot", params={"table": t["SourceTable"], "time": t["EventStartTime"],
                                                     "value": ATTACKER, "key": t["SourceRecordKey"], "group": t["SourceGroup"]}))
    assert len(rows) == 1 and ATTACKER in json.dumps(rows[0])


# ------------------------------------------------------------------ onboarding workflow
def test_catalog(client):
    r = ok(client.get("/api/v1/catalog/solutions", params={"q": "okta"}))
    assert r["stats"]["solutions"] > 300 and r["stats"]["tables"] > 1000
    plan = ok(client.get(f"/api/v1/catalog/solutions/{r['items'][0]['folder']}/plan"))
    assert any(t["name"] == "OktaV2_CL" and t["asimParsers"] for t in plan["tables"])


def test_deployment_needs_approval(client):
    a = ok(client.post("/api/v1/deployments", json={"solutions": [{"name": "Okta Single Sign-On"}],
                                                    "tables": [{"name": "OktaV2_CL", "plan": "Lake", "retentionDays": 365}]}))
    assert ok(client.get("/api/v1/approvals", params={"status": "pending"}))
    # a viewer cannot approve
    r = client.post(f"/api/v1/approvals/{a['approval']}/approve", headers={"X-LakeHunt-Demo-Role": "viewer"})
    assert r.status_code == 403
    done = ok(client.post(f"/api/v1/approvals/{a['approval']}/approve"))
    assert done["status"] == "executed" and done["result"]["tables"][0]["plan"] == "Auxiliary"


def test_guided_review_of_new_source(client):
    p = ok(client.get("/api/v1/tables/BadgeReader_CL/proposals"))
    assert p["preset"] == "physical" and p["path"] == "kv"
    cards = {c["field"]: c for c in p["cards"]}
    assert cards["RawData.holder"]["recommended"] == {"entity": "user", "role": "Actor", "asim": "ActorUsername"}
    assert cards["RawData.reader"]["recommended"]["role"] == "Dvc"
    assert cards["RawData.result"]["decision"] == "result"
    vals = {v["value"]: v["suggested"] for v in cards["RawData.result"]["values"]}
    assert vals == {"granted": "Success", "denied": "Failure"}
    # each entity card offers the common alternatives in plain words
    assert {c["value"] for c in cards["RawData.holder"]["roleChoices"]} >= {"Actor", "Target", "Unknown"}


def _badge_decisions():
    return {"id": "BadgeReader_CL:main", "preset": "physical", "vendor": "Contoso", "product": "Badge readers",
            "fields": [{"field": "RawData.holder", "kind": "kv", "entity": "user", "role": "Actor", "asim": "ActorUsername"},
                       {"field": "RawData.reader", "kind": "kv", "entity": "ip", "role": "Dvc", "asim": "DvcIpAddr"}],
            "result": {"field": "RawData.result", "kind": "kv", "map": {"granted": "Success", "denied": "Failure"}},
            "text_column": "RawData", "templates": []}


def test_preview_then_submit_approve_validate(client):
    pv = ok(client.post("/api/v1/tables/BadgeReader_CL/preview", json={"decisions": _badge_decisions()}))
    assert not pv["errors"] and pv["coverage"]["ExtractionRate"] >= 0.9 and pv["coverage"]["TemplateMatchRate"] >= 0.99
    assert pv["byEntity"].get("user:Actor") and pv["byEntity"].get("ip:Dvc")
    rec = ok(client.post("/api/v1/registry/from-decisions/BadgeReader_CL", json={"decisions": _badge_decisions(), "submit": True}))
    assert rec["approval"]
    assert ok(client.get("/api/v1/onboarding/BadgeReader_CL"))["stage"]["stage"] == "registry"
    ok(client.post(f"/api/v1/approvals/{rec['approval']}/approve"))
    assert ok(client.get("/api/v1/registry/BadgeReader_CL:main"))["status"] == "live"
    v = ok(client.post("/api/v1/validation/BadgeReader_CL:main/run", json={"handCheck": True}))
    assert v["passed"], v["checks"]
    assert ok(client.get("/api/v1/onboarding/BadgeReader_CL"))["stage"]["stage"] == "live"
    # the badge reader now answers who-was-where questions for jsmith
    r = ok(client.get("/api/v1/hunt/value", params={"v": "jsmith@contoso.com"}))
    assert any(s["SourceGroup"] == "BadgeReader_CL:main" and "Actor" in s["Roles"] for s in r["sources"])


def test_drift_and_noise_exclusion(client):
    d = ok(client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                     "params": {"name": "explain_drift", "arguments": {"group": "VpnAppliance_CL:raw"}}}))
    res = json.loads(d["result"]["content"][0]["text"])
    assert res["unmatchedTemplates"] and "keepalive" in res["unmatchedTemplates"][0]["template"]
    a = ok(client.post("/api/v1/registry/VpnAppliance_CL:raw/exclude", json={"text": "keepalive"}))
    ok(client.post(f"/api/v1/approvals/{a['approval']}/approve"))
    cov = {c["SourceGroup"]: c for c in ok(client.get("/api/v1/coverage"))}
    assert cov["VpnAppliance_CL:raw"]["Status"] == "ok"


def test_viewer_cannot_change_registry(client):
    r = client.put("/api/v1/registry", json={"group": {"id": "x:y", "table": "Syslog"}}, headers={"X-LakeHunt-Demo-Role": "viewer"})
    assert r.status_code == 403


# ------------------------------------------------------------------ MCP
def test_mcp_lists_and_calls_tools(client):
    init = ok(client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                        "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}}))
    assert init["result"]["serverInfo"]["name"] == "lakehunt"
    tools = ok(client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}))["result"]["tools"]
    assert {"hunt_value", "propose_mapping", "save_draft_mapping"} <= {t["name"] for t in tools}
    viewer_tools = ok(client.post("/mcp", json={"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
                                  headers={"X-LakeHunt-Demo-Role": "viewer"}))["result"]["tools"]
    assert "save_draft_mapping" not in {t["name"] for t in viewer_tools}
    r = ok(client.post("/mcp", json={"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                                     "params": {"name": "hunt_value", "arguments": {"value": ATTACKER}}}))
    assert not r["result"]["isError"] and ATTACKER in r["result"]["content"][0]["text"]


# ------------------------------------------------------------------ generated KQL
def test_generated_kql_parses(client, tmp_path):
    node = shutil.which("node")
    lib = os.environ.get("KUSTO_LIB") or str(Path(__file__).parent / "node_modules")
    if not node or not Path(lib, "@kusto/language-service-next").exists():
        pytest.skip("Node.js or @kusto/language-service-next not available")
    b = ok(client.get("/api/v1/build"))
    core = app.state.core
    files = core.build()["files"]
    for name, text in files.items():
        if name.endswith(".kql"):
            (tmp_path / name.replace("/", "_")).write_text(text)
    import yaml
    for t in yaml.safe_load(files["mcp/tools.yaml"])["tools"]:
        (tmp_path / f"tool_{t['name']}.kql").write_text(t["query"].replace("{SourceTable}", "Syslog").replace("{Table}", "Syslog")
                                                         .replace("{EventStartTime}", "2026-10-18T09:20:00Z"))
    # schemas: demo tables + index tables
    from app.kit.generate import ENTITY_COLUMNS, EVENT_COLUMNS
    kt = {"string": "string", "int": "int", "datetime": "datetime", "real": "real", "bool": "bool"}
    schemas = {t["name"]: "(" + ", ".join(f"{c['name']}:{kt.get(c['type'], 'string')}" for c in t["columns"]) + ")"
               for t in core.p.tables()}
    ent = "(TimeGenerated:datetime, " + ", ".join(f"{c}:{t}" for c, t in ENTITY_COLUMNS) + ")"
    evt = "(TimeGenerated:datetime, " + ", ".join(f"{c}:{t}" for c, t in EVENT_COLUMNS) + ")"
    schemas.update({"HuntEntity_SPRK": ent, "HuntEntity_KQL": ent, "HuntEvent_SPRK": evt, "HuntEvent_KQL": evt,
                    "HuntCoverage_SPRK": "(TimeGenerated:datetime, SourceGroup:string, SourceTable:string, Tier:int, RawRows:long, "
                                         "IndexedRows:long, ExtractionRate:real, TemplateMatchRate:real, UnknownRoleShare:real, "
                                         "LastIndexed:datetime, Status:string)"})
    (tmp_path / "schemas.json").write_text(json.dumps(schemas))
    kqls = sorted(str(p) for p in tmp_path.glob("*.kql"))
    assert len(kqls) >= 15 and b["budget"]["kqlJobs"] >= 10
    r = subprocess.run([node, str(Path(__file__).parent / "kql_check.js"), "--schemas", str(tmp_path / "schemas.json"), *kqls],
                       capture_output=True, text=True, env={**os.environ, "KUSTO_LIB": lib})
    assert r.returncode == 0, r.stdout[-3000:]
