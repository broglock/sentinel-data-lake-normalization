"""Demo provider: synthetic tables in memory, indexed by the Python engine."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from app.demo.demo_data import build
from app.engine import coverage as cov
from app.engine import hunt as H
from app.engine.indexer import index_parts
from app.providers.base import Provider

PLANS = {"SecurityEvent": "Analytics", "SigninLogs": "Analytics", "CommonSecurityLog": "Analytics"}


def _type(v: Any) -> str:
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "real"
    if isinstance(v, datetime):
        return "datetime"
    return "string"


class DemoProvider(Provider):
    mode = "demo"

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.raw: dict[str, list[dict]] = build()
        self.extra_tables: dict[str, dict] = {}
        self.solutions: list[dict] = [
            {"name": n, "version": "", "installedOn": "2026-09-01"} for n in
            ["Windows Security Events", "Microsoft Entra ID", "Common Event Format",
             "Fortinet FortiGate Next-Generation Firewall connector for Microsoft Sentinel",
             "PaloAlto-PAN-OS", "Syslog", "Amazon Web Services", "Okta Single Sign-On"]]
        self.ents: list[dict] = []
        self.evs: list[dict] = []
        self.by_group: dict[str, list[dict]] = {}      # HuntEntity rows (rollup and _stats) per group
        self.occ_by_group: dict[str, list[dict]] = {}  # occurrence rows per group (canary only)
        self.raw_by_group: dict[str, list[dict]] = {}
        self.canary_seq = 0

    # ------------------------------------------------------------ inventory
    def tables(self) -> list[dict]:
        out = []
        with self.lock:
            for name, rows in self.raw.items():
                last = max((r["TimeGenerated"] for r in rows), default=None)
                cols = [{"name": k, "type": _type(v)} for k, v in rows[0].items()] if rows else []
                out.append({"name": name, "plan": PLANS.get(name, "Lake"), "rows7d": len(rows),
                            "lastSeen": last.strftime("%Y-%m-%dT%H:%M:%SZ") if last else None, "columns": cols})
            for name, t in self.extra_tables.items():
                if name not in self.raw:
                    out.append({"name": name, "plan": t["plan"], "rows7d": 0, "lastSeen": None, "columns": t["columns"]})
        return sorted(out, key=lambda t: t["name"])

    def sample(self, table: str, n: int = 500) -> list[dict]:
        with self.lock:
            rows = self.raw.get(table, [])
            return sorted(rows, key=lambda r: r["TimeGenerated"], reverse=True)[:n]

    # ------------------------------------------------------------ index
    def reindex(self, groups: list[dict], vocab: dict) -> dict:
        ents, evs, by_group, occ_by_group, raw_by_group = [], [], {}, {}, {}
        with self.lock:
            for g in groups:
                p = index_parts(self.raw.get(g["table"], []), g, vocab)
                ents += p["entity"]
                evs += p["event"]
                by_group[g["id"]], occ_by_group[g["id"]], raw_by_group[g["id"]] = p["entity"], p["occ"], p["base"]
            self.ents, self.evs, self.by_group, self.occ_by_group, self.raw_by_group = ents, evs, by_group, occ_by_group, raw_by_group
        return {"groups": len(groups), "entityRows": len(ents), "eventRows": len(evs)}

    def coverage(self, groups: list[dict]) -> list[dict]:
        from app.config import settings
        with self.lock:
            return [cov.group_coverage(g, self.by_group.get(g["id"], []), settings.min_extraction,
                                       settings.min_template_match) for g in groups]

    def history(self, group: dict) -> list[dict]:
        with self.lock:
            return cov.daily_history(group, self.by_group.get(group["id"], []))

    # ------------------------------------------------------------ hunting
    def hunt(self, tool: str, **p: Any) -> list[dict]:
        with self.lock:
            ents, evs = self.ents, self.evs
        days = float(p.get("days", 7))
        if tool == "hunt_value":
            return H.hunt_value(ents, p["value"], days)
        if tool == "hunt_entity":
            return H.hunt_entity(ents, p["entity_type"], p["value"], p.get("role", "*"), days)
        if tool == "auth_events":
            return H.auth_events(evs, p["user"], p.get("result", "*"), days)
        if tool == "network_events":
            return H.network_events(evs, p["ip"], days)
        if tool == "timeline":
            return H.timeline(ents, p["value"], days)
        if tool == "related":
            return H.related(ents, p["value"], days)
        if tool == "search_raw":
            text, table = p["text"].lower(), p["table"]
            since = datetime.now(timezone.utc) - timedelta(hours=float(p.get("hours", 24)))
            with self.lock:
                rows = [r for r in self.raw.get(table, []) if r["TimeGenerated"] >= since
                        and text in json.dumps(r, default=str).lower()]
            return [_jsonable(r) for r in rows[:100]]
        raise ValueError(f"unknown tool {tool}")

    def index_rows_for_group(self, group_id: str, limit: int = 20) -> list[dict]:
        with self.lock:
            rows = [r for r in self.by_group.get(group_id, []) if r["EntityType"] != "_stats"]
            rows = sorted(rows, key=lambda r: r["Hour"], reverse=True)
            return [_jsonable(r) for r in rows[:limit]]

    def pivot(self, table: str, event_time: str, value: str, record_key: str = "", group: dict | None = None,
              last_time: str = "") -> list[dict]:
        """Original rows behind an index row: by record key (HuntEvent row or a SampleKeys entry),
        otherwise by time range and value (a HuntEntity row covers up to one hour)."""
        keys = [k for k in record_key.split(",") if k]
        with self.lock:
            if group and keys:
                return [_jsonable({k: v for k, v in r.items() if not k.startswith("_")})
                        for r in self.raw_by_group.get(group["id"], []) if r["_SourceRecordKey"] in keys][:20]
            t0 = datetime.fromisoformat(event_time.replace("Z", "+00:00"))
            t1 = datetime.fromisoformat((last_time or event_time).replace("Z", "+00:00"))
            return [_jsonable(r) for r in self.raw.get(table, [])
                    if t0 - timedelta(seconds=1) <= r["TimeGenerated"] <= t1 + timedelta(seconds=1)
                    and value.lower() in json.dumps(r, default=str).lower()][:20]

    # ------------------------------------------------------------ tenant changes (simulated)
    def installed_solutions(self) -> list[dict]:
        return list(self.solutions)

    def install_solution(self, solution: dict) -> dict:
        with self.lock:
            if not any(s["name"] == solution["name"] for s in self.solutions):
                self.solutions.append({"name": solution["name"], "version": solution.get("version", ""),
                                       "installedOn": datetime.now(timezone.utc).strftime("%Y-%m-%d")})
        return {"simulated": True, "steps": [
            f"GET contentProductPackages for '{solution['name']}' with packagedContent",
            "PUT Microsoft.Resources/deployments with the packagedContent template (incremental)",
            "Connector definitions, parsers and content templates are now installed"]}

    def create_table(self, name: str, columns: list[dict], plan: str, retention_days: int) -> dict:
        with self.lock:
            self.extra_tables[name] = {"plan": plan, "columns": columns, "retention": retention_days}
        return {"simulated": True, "table": name, "plan": plan, "retentionDays": retention_days,
                "request": f"PUT .../workspaces/<workspace>/tables/{name}"}

    # ------------------------------------------------------------ validation
    def canary(self, group: dict, vocab: dict, value: str | None = None) -> dict:
        """Clone a recent raw row of the group, swap its source IP (or first entity value) for a
        canary value, add it to the raw table and re-index the group."""
        with self.lock:
            ents = self.occ_by_group.get(group["id"], [])
            pick = next((e for e in ents if e["EntityType"] == "ip"), None) or (ents[0] if ents else None)
            if not pick:
                return {"ok": False, "reason": "The group has no indexed rows to copy"}
            raw = next((r for r in self.raw_by_group.get(group["id"], []) if r["_SourceRecordKey"] == pick["SourceRecordKey"]), None)
            if raw is None:
                return {"ok": False, "reason": "Raw row not found"}
            self.canary_seq += 1
            canary = value or (f"192.0.2.{200 + self.canary_seq % 50}" if pick["EntityType"] == "ip"
                               else f"canary{self.canary_seq}")
            row = {k: v for k, v in raw.items() if not k.startswith("_")}
            s = json.dumps(row, default=str).replace(pick["Value"], canary)
            new = json.loads(s)
            new["TimeGenerated"] = datetime.now(timezone.utc) - timedelta(minutes=1)
            for k, v in row.items():
                if isinstance(v, int) and not isinstance(v, bool):
                    new[k] = v
            self.raw[group["table"]].append(new)
        # re-index just this group
        p = index_parts(self.raw[group["table"]], group, vocab)
        with self.lock:
            others = [x for x in self.ents if x["SourceGroup"] != group["id"]]
            other_ev = [x for x in self.evs if x["SourceGroup"] != group["id"]]
            self.ents, self.evs = others + p["entity"], other_ev + p["event"]
            self.by_group[group["id"]], self.occ_by_group[group["id"]] = p["entity"], p["occ"]
            self.raw_by_group[group["id"]] = p["base"]
        return {"ok": True, "value": canary, "entityType": pick["EntityType"], "replaced": pick["Value"],
                "raw": _jsonable(new)}


def _jsonable(r: dict) -> dict:
    return {k: (v.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z" if isinstance(v, datetime) else v)
            for k, v in r.items() if not k.startswith("_")}
