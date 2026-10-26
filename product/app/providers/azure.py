"""Live provider: Azure Resource Manager, the Sentinel data lake KQL API and the Log Analytics
query API, called with the app's managed identity (DefaultAzureCredential).

Surfaces used (verify in a lab tenant before production; several are preview):
  ARM  GET/PUT  .../workspaces/{ws}/tables[/{name}]                      api-version 2023-01-01-preview
  ARM  GET      .../workspaces/{ws}/providers/Microsoft.SecurityInsights/contentProductPackages
  ARM  GET      .../contentProductPackages/{id}?$expand=properties/packagedContent
  ARM  PUT      .../resourceGroups/{rg}/providers/Microsoft.Resources/deployments/{name}
  ARM  GET      .../workspaces/{ws}/providers/Microsoft.SecurityInsights/contentPackages
  Lake POST     https://api.securityplatform.microsoft.com/lake/kql/v2/rest/query   {csl, db}
  LA   POST     https://api.loganalytics.io/v1/workspaces/{id}/query                  {query}
KQL jobs and notebook jobs have no public create API at the time of writing, so the app builds
the job definitions and the operator creates them in the Defender portal (Deploy screen).
"""
from __future__ import annotations

import re
import time
from typing import Any

import httpx
import yaml

from app.config import APP_DIR, settings
from app.providers.base import Provider

TABLE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{1,62}$")
TOOLS = {t["name"]: t for t in yaml.safe_load(open(APP_DIR / "kit" / "tools.yaml", encoding="utf-8"))["tools"]}


def kql_str(v: Any) -> str:
    """Escape a value placed inside a KQL double-quoted string."""
    return str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


class AzureProvider(Provider):
    mode = "live"

    def __init__(self) -> None:
        from azure.identity import DefaultAzureCredential
        self.cred = DefaultAzureCredential(exclude_interactive_browser_credential=True)
        self.http = httpx.Client(timeout=300)
        self._tok: dict[str, tuple[str, float]] = {}

    # ------------------------------------------------------------ plumbing
    def _token(self, scope: str) -> str:
        tok, exp = self._tok.get(scope, ("", 0))
        if time.time() > exp - 120:
            t = self.cred.get_token(scope)
            tok, exp = t.token, t.expires_on
            self._tok[scope] = (tok, exp)
        return tok

    def _arm(self, method: str, path: str, api: str, body: dict | None = None, params: dict | None = None) -> dict:
        url = settings.arm_endpoint + path
        r = self.http.request(method, url, params={"api-version": api, **(params or {})}, json=body,
                              headers={"Authorization": f"Bearer {self._token(settings.arm_endpoint + '/.default')}"})
        if r.status_code >= 400:
            raise RuntimeError(f"ARM {method} {path} -> {r.status_code}: {r.text[:500]}")
        return r.json() if r.content else {}

    def _arm_list(self, path: str, api: str, params: dict | None = None) -> list[dict]:
        out, page = [], self._arm("GET", path, api, params=params)
        out += page.get("value", [])
        while page.get("nextLink"):
            r = self.http.get(page["nextLink"], headers={"Authorization": f"Bearer {self._token(settings.arm_endpoint + '/.default')}"})
            page = r.json()
            out += page.get("value", [])
        return out

    def lake(self, csl: str) -> list[dict]:
        db = f"{settings.workspace_name}-{settings.workspace_id}"
        r = self.http.post(settings.lake_query_url, json={"csl": csl, "db": db},
                           headers={"Authorization": f"Bearer {self._token(settings.lake_scope)}"})
        if r.status_code >= 400:
            raise RuntimeError(f"Lake query -> {r.status_code}: {r.text[:500]}")
        return parse_kusto(r.json())

    def analytics(self, query: str) -> list[dict]:
        url = settings.la_query_url.format(workspace_id=settings.workspace_id)
        r = self.http.post(url, json={"query": query}, headers={"Authorization": f"Bearer {self._token(settings.la_scope)}"})
        if r.status_code >= 400:
            raise RuntimeError(f"Log Analytics query -> {r.status_code}: {r.text[:500]}")
        return parse_kusto(r.json())

    # ------------------------------------------------------------ inventory
    def tables(self) -> list[dict]:
        items = self._arm_list(settings.workspace_arm_id + "/tables", settings.tables_api_version)
        usage = {}
        try:
            for r in self.analytics("Usage | where TimeGenerated > ago(7d) | summarize MB = sum(Quantity), "
                                    "LastSeen = max(TimeGenerated) by DataType"):
                usage[r["DataType"]] = r
        except Exception:
            pass
        out = []
        for t in items:
            p = t.get("properties", {})
            name = t.get("name", "")
            if p.get("schema", {}).get("tableType") == "SearchResults":
                continue
            u = usage.get(name, {})
            out.append({"name": name, "plan": p.get("plan", ""), "retentionDays": p.get("totalRetentionInDays"),
                        "mb7d": u.get("MB"), "rows7d": None, "lastSeen": u.get("LastSeen"),
                        "columns": [{"name": c["name"], "type": c.get("type", "string")}
                                    for c in (p.get("schema", {}).get("columns") or []) +
                                    (p.get("schema", {}).get("standardColumns") or [])]})
        return sorted(out, key=lambda t: t["name"])

    def sample(self, table: str, n: int = 500) -> list[dict]:
        if not TABLE_NAME.match(table):
            raise ValueError("bad table name")
        return self.lake(f"{table} | where TimeGenerated > ago(1d) | take {int(n)}")

    # ------------------------------------------------------------ index (built by lake jobs)
    def reindex(self, groups: list[dict], vocab: dict) -> dict:
        return {"live": True, "message": "In live mode the index is built by the KQL jobs and notebook jobs "
                                         "created from the Deploy screen. Nothing runs inside this app."}

    def coverage(self, groups: list[dict]) -> list[dict]:
        rows = self.lake(TOOLS["coverage"]["query"].replace("{SourceGroup}", "*"))
        known = {g["id"] for g in groups}
        for r in rows:
            r["InRegistry"] = r.get("SourceGroup") in known
        return rows

    def history(self, group: dict) -> list[dict]:
        g = kql_str(group["id"])
        return self.lake(f'{settings.coverage_table} | where TimeGenerated > ago(28d) and SourceGroup == "{g}" '
                         f'| summarize arg_max(TimeGenerated, *) by day = startofday(TimeGenerated) '
                         f'| project day, raw = RawRows, indexed = IndexedRows, extraction = ExtractionRate | order by day asc')

    # ------------------------------------------------------------ hunting
    def hunt(self, tool: str, **p: Any) -> list[dict]:
        days = max(1, min(int(float(p.get("days", 7))), 90))
        if tool in ("timeline", "related"):
            return self.lake(self._extra(tool, kql_str(p["value"]), days))
        t = TOOLS[tool if tool != "search_raw" else "search_raw"]
        params = {"LookbackDays": str(days), "LookbackHours": str(max(1, min(int(float(p.get("hours", 24))), 168)))}
        if tool == "hunt_value":
            params["Value"] = kql_str(p["value"])
        elif tool == "hunt_entity":
            if p["entity_type"] not in ("ip", "host", "user", "hash", "url", "domain", "email"):
                raise ValueError("bad entity type")
            if p.get("role", "*") not in ("Src", "Dst", "Actor", "Target", "Dvc", "Unknown", "*"):
                raise ValueError("bad role")
            params.update(EntityType=p["entity_type"], Value=kql_str(p["value"]), Role=p.get("role", "*"))
        elif tool == "auth_events":
            if p.get("result", "*") not in ("Success", "Failure", "*"):
                raise ValueError("bad result")
            params.update(User=kql_str(p["user"]), Result=p.get("result", "*"))
        elif tool == "network_events":
            params["Ip"] = kql_str(p["ip"])
        elif tool == "search_raw":
            if not TABLE_NAME.match(p["table"]):
                raise ValueError("bad table name")
            params.update(Table=p["table"], Text=kql_str(p["text"]))
        q = t["query"]
        for k, v in params.items():
            q = q.replace("{" + k + "}", v)
        return self.lake(q)

    def _extra(self, tool: str, v: str, days: int) -> str:
        head = ('let HuntIndexEntity = union isfuzzy=true HuntEntity_SPRK, HuntEntity_KQL;\n'
                f'let raw = tolower(trim(@"\\s", "{v}"));\n'
                'let short = case(raw contains @"\\", tostring(split(raw, @"\\")[1]), raw contains "@", tostring(split(raw, "@")[0]), raw);\n'
                f'let hits = HuntIndexEntity | where EventStartTime > ago({days}d) '
                '| where ValueNorm in (raw, short) or tolower(Value) == raw;\n')
        if tool == "timeline":
            return head + (f'hits | join kind=inner (HuntIndexEntity | where EventStartTime > ago({days}d) '
                           '| project SourceGroup, SourceRecordKey, E = strcat(EntityType, ":", Role, "=", Value)) '
                           'on SourceGroup, SourceRecordKey\n'
                           '| summarize Entities = make_set(E, 20) by EventStartTime, SourceTable, SourceGroup, EventType, '
                           'EventResult, MatchedAs = strcat(EntityType, ":", Role), Tier = MappingTier, SourceRecordKey\n'
                           '| order by EventStartTime asc | take 500')
        return head + (f'hits | distinct SourceGroup, SourceRecordKey | join kind=inner (HuntIndexEntity '
                       f'| where EventStartTime > ago({days}d)) on SourceGroup, SourceRecordKey\n'
                       '| where ValueNorm !in (raw, short)\n'
                       '| summarize Events = count(), Sources = make_set(SourceGroup), Roles = make_set(Role) '
                       'by EntityType, Value = ValueNorm | order by array_length(Sources) desc, Events desc | take 25')

    def index_rows_for_group(self, group_id: str, limit: int = 20) -> list[dict]:
        return self.lake(f'union isfuzzy=true HuntEntity_SPRK, HuntEntity_KQL | where EventStartTime > ago(1d) and SourceGroup == "{kql_str(group_id)}" '
                         f'| take {int(limit)}')

    def pivot(self, table: str, event_time: str, value: str, record_key: str = "", group: dict | None = None) -> list[dict]:
        if not TABLE_NAME.match(table):
            raise ValueError("bad table name")
        if group and record_key and group.get("record_key"):
            tc = group.get("time_column", "TimeGenerated")
            return self.lake(f'let t = todatetime("{kql_str(event_time)}");\n{table}\n'
                             f'| where {tc} between ((t - 1s) .. (t + 1s))\n'
                             f'| where tostring({group["record_key"]}) == "{kql_str(record_key)}"\n| take 5')
        q = TOOLS["pivot_raw"]["query"]
        for k, v in {"SourceTable": table, "EventStartTime": kql_str(event_time), "Value": kql_str(value)}.items():
            q = q.replace("{" + k + "}", v)
        return self.lake(q)

    # ------------------------------------------------------------ tenant changes
    def installed_solutions(self) -> list[dict]:
        items = self._arm_list(settings.workspace_arm_id + "/providers/Microsoft.SecurityInsights/contentPackages",
                               settings.content_api_version)
        return [{"name": i["properties"].get("displayName"), "version": i["properties"].get("version"),
                 "contentId": i["properties"].get("contentId")} for i in items]

    def install_solution(self, solution: dict) -> dict:
        base = settings.workspace_arm_id + "/providers/Microsoft.SecurityInsights/contentProductPackages"
        name = solution["name"].replace("'", "''")
        found = self._arm_list(base, settings.content_api_version,
                               params={"$filter": f"properties/displayName eq '{name}'"})
        found = [f for f in found if f["properties"].get("contentKind") == "Solution"] or found
        if not found:
            raise RuntimeError(f"Solution '{solution['name']}' not found in the Content hub catalog")
        pkg = self._arm("GET", f"{base}/{found[0]['name']}", settings.content_api_version,
                        params={"$expand": "properties/packagedContent"})
        template = pkg["properties"].get("packagedContent")
        if not template:
            raise RuntimeError("Catalog entry has no packagedContent")
        dep = re.sub(r"[^A-Za-z0-9-]", "-", f"lakehunt-{pkg['properties'].get('contentId', 'solution')}")[:60]
        body = {"properties": {"mode": "Incremental", "template": template, "parameters": {
            "workspace": {"value": settings.workspace_name},
            "workspace-location": {"value": settings.workspace_location}}}}
        path = (f"/subscriptions/{settings.subscription_id}/resourceGroups/{settings.resource_group}"
                f"/providers/Microsoft.Resources/deployments/{dep}")
        res = self._arm("PUT", path, settings.deployments_api_version, body)
        return {"deployment": dep, "provisioningState": res.get("properties", {}).get("provisioningState"),
                "package": pkg["properties"].get("displayName"), "version": pkg["properties"].get("version")}

    def create_table(self, name: str, columns: list[dict], plan: str, retention_days: int) -> dict:
        if not TABLE_NAME.match(name):
            raise ValueError("bad table name")
        cols = [c for c in columns if c["name"] not in ("TenantId", "Type", "_ResourceId")]
        if not any(c["name"] == "TimeGenerated" for c in cols):
            cols.insert(0, {"name": "TimeGenerated", "type": "datetime"})
        body = {"properties": {"plan": plan, "totalRetentionInDays": retention_days,
                               "schema": {"name": name, "columns": cols}}}
        res = self._arm("PUT", f"{settings.workspace_arm_id}/tables/{name}", settings.tables_api_version, body)
        return {"table": name, "plan": plan, "provisioningState": res.get("properties", {}).get("provisioningState")}

    # ------------------------------------------------------------ validation
    def canary(self, group: dict, vocab: dict, value: str | None = None) -> dict:
        if not value:
            return {"ok": False, "needsOperator": True,
                    "reason": "Generate a test event on the source with a value you choose (for example a sign-in "
                              "from a known test IP), wait for the next index run, then enter that value here."}
        hits = [h for h in self.hunt("hunt_value", value=value, days=1) if h.get("SourceGroup") == group["id"]]
        return {"ok": bool(hits), "value": value, "hits": hits}


def parse_kusto(payload: Any) -> list[dict]:
    """Rows from a Kusto v1 ({Tables:[...]}), v2 (list of frames) or Log Analytics ({tables:[...]}) response."""
    def rows_of(cols, rows):
        names = [c.get("ColumnName") or c.get("name") for c in cols]
        return [dict(zip(names, r)) for r in rows]
    if isinstance(payload, dict):
        tabs = payload.get("Tables") or payload.get("tables") or []
        if tabs:
            t = tabs[0]
            return rows_of(t.get("Columns") or t.get("columns"), t.get("Rows") or t.get("rows") or [])
        return []
    if isinstance(payload, list):
        for f in payload:
            if f.get("FrameType") == "DataTable" and f.get("TableKind") == "PrimaryResult":
                return rows_of(f["Columns"], f["Rows"])
    return []
