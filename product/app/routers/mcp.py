"""MCP server (Streamable HTTP, stateless JSON responses) at /mcp.

Lets AI agents (Security Copilot, Claude, Copilot Studio, custom agents) hunt across the index
and work the onboarding queue. Tools that read are open to Viewers. Tools that change anything
only ever create drafts or approval requests: an agent can propose a mapping, preview it, save
it as a draft and submit it, but an Admin approves every registry change and tenant change.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from app.auth import RANK, User, current_user
from app.config import settings

router = APIRouter()
PROTOCOL = "2025-06-18"

INSTRUCTIONS = (
    "Hunt across every log source through the normalized index (an hourly rollup of entity counts, plus "
    "per-event rows for Tier 1 sources). Start with hunt_value, report how many "
    "sources matched and at which tier, treat Role=Unknown as unknown, and fetch originals with pivot_raw before "
    "quoting raw fields. Run search_raw on tables listed by coverage before saying a value was not seen. "
    "For onboarding: list_sources, then propose_mapping, adjust the decisions, preview_mapping until extraction "
    "and template match pass, then save_draft_mapping with submit=true. A human approves every change."
)

S = {"type": "string"}
N = {"type": "number"}
TOOLS: list[dict] = [
    {"name": "hunt_value", "role": "viewer", "description": "Every log source where a value (IP, user in any format, host, hash, URL, domain) appeared, with roles, tiers and results.",
     "inputSchema": {"type": "object", "properties": {"value": S, "days": N}, "required": ["value"]}},
    {"name": "hunt_entity", "role": "viewer", "description": "One entity type, optionally in one role (Src, Dst, Actor, Target, Dvc, Unknown or *), across every source.",
     "inputSchema": {"type": "object", "properties": {"entity_type": {"type": "string", "enum": ["ip", "host", "user", "hash", "url", "domain", "email"]},
                                                      "value": S, "role": S, "days": N}, "required": ["entity_type", "value"]}},
    {"name": "auth_events", "role": "viewer", "description": "Sign-in events for a user (any format) with result and source IP, from Tier 1 sources.",
     "inputSchema": {"type": "object", "properties": {"user": S, "result": {"type": "string", "enum": ["Success", "Failure", "*"]}, "days": N}, "required": ["user"]}},
    {"name": "network_events", "role": "viewer", "description": "Network sessions involving an IP, with direction, port and device action.",
     "inputSchema": {"type": "object", "properties": {"ip": S, "days": N}, "required": ["ip"]}},
    {"name": "timeline", "role": "viewer", "description": "Every indexed event touching a value, oldest first, with the other entities in each event.",
     "inputSchema": {"type": "object", "properties": {"value": S, "days": N}, "required": ["value"]}},
    {"name": "related", "role": "viewer", "description": "Entities that appear in the same sampled events as a value: the next things to pivot on.",
     "inputSchema": {"type": "object", "properties": {"value": S, "days": N}, "required": ["value"]}},
    {"name": "pivot_raw", "role": "viewer", "description": "The original log rows behind an index row. Use SourceTable, EventStartTime (or FirstSeen) as time, LastSeen as until, Value, SourceGroup, and SourceRecordKey or comma-separated SampleKeys as key.",
     "inputSchema": {"type": "object", "properties": {"table": S, "time": S, "until": S, "value": S, "key": S, "group": S}, "required": ["table", "time", "value"]}},
    {"name": "search_raw", "role": "analyst", "description": "Free-text search of one raw table, for values the index did not map. Keep hours small.",
     "inputSchema": {"type": "object", "properties": {"table": S, "text": S, "hours": N}, "required": ["table", "text"]}},
    {"name": "coverage", "role": "viewer", "description": "How deeply each source is indexed: tier, extraction rate, template match rate, status.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "list_sources", "role": "viewer", "description": "Every table with its mapping status, onboarding stage and available ASIM parsers.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "propose_mapping", "role": "viewer", "description": "Field-by-field recommendations for a table, with evidence (samples, value class, fill rate) and the common alternatives. Returns decision cards and mined templates.",
     "inputSchema": {"type": "object", "properties": {"table": S, "preset": {"type": "string", "enum": ["authentication", "network", "web", "audit", "physical", "other"]}}, "required": ["table"]}},
    {"name": "preview_mapping", "role": "analyst", "description": "Run decisions (or a registry group) over sample rows: coverage numbers, entity counts, raw-vs-index pairs and the generated KQL. Changes nothing.",
     "inputSchema": {"type": "object", "properties": {"table": S, "decisions": {"type": "object"}, "group": {"type": "object"}}, "required": ["table"]}},
    {"name": "save_draft_mapping", "role": "analyst", "description": "Save decisions as a draft registry entry; with submit=true also request Admin approval. Never goes live without a human.",
     "inputSchema": {"type": "object", "properties": {"table": S, "decisions": {"type": "object"}, "submit": {"type": "boolean"}, "note": S}, "required": ["table", "decisions"]}},
    {"name": "validate_source", "role": "analyst", "description": "Run the four post-onboarding checks for a live group (coverage, hand check pairs for a human, canary, pivot).",
     "inputSchema": {"type": "object", "properties": {"group": S, "canary_value": S}, "required": ["group"]}},
    {"name": "explain_drift", "role": "viewer", "description": "Why a source's coverage dropped: unmatched message shapes with suggested templates, missing or empty mapped columns, daily history.",
     "inputSchema": {"type": "object", "properties": {"group": S}, "required": ["group"]}},
    {"name": "plan_connector", "role": "viewer", "description": "For a Content hub solution: the tables it writes, their schemas, recommended tier, ASIM parsers and the mapping path.",
     "inputSchema": {"type": "object", "properties": {"query": S}, "required": ["query"]}},
]


def _call(core, user: User, name: str, a: dict) -> Any:
    p = core.p
    if name in ("hunt_value", "hunt_entity", "auth_events", "network_events", "timeline", "related", "search_raw"):
        return p.hunt(name, **a)
    if name == "pivot_raw":
        from app.kit.generate import complete_group
        g = next((x for x in core.index_groups() if x["id"] == a.get("group")), None)
        return p.pivot(a["table"], a["time"], a["value"], a.get("key", ""), complete_group(g) if g else None,
                       a.get("until", ""))
    if name == "coverage":
        return core.coverage()
    if name == "list_sources":
        return core.table_overview()
    if name == "propose_mapping":
        r = core.proposals(a["table"], a.get("preset"))
        return {k: r[k] for k in ("table", "rows", "preset", "path", "pathHelp", "cards", "templates", "asimParsers", "textColumn")}
    if name == "preview_mapping":
        r = core.preview(a["table"], a.get("decisions"), a.get("group"))
        r.pop("kql", None) if len(json.dumps(r, default=str)) > 60000 else None
        return r
    if name == "save_draft_mapping":
        from app.engine import guide
        rows = p.sample(a["table"], 1)
        g = guide.build_group(a["table"], a["decisions"], list(rows[0].keys()) if rows else [])
        rec = core.save_draft(g, f"{user.name} (agent)", a.get("note", "drafted by agent"))
        if a.get("submit"):
            rec["approval"] = core.submit(g["id"], f"{user.name} (agent)")["approval"]
        return rec
    if name == "validate_source":
        return core.validate(a["group"], f"{user.name} (agent)", a.get("canary_value"), None)
    if name == "explain_drift":
        return core.drift(a["group"])
    if name == "plan_connector":
        hits = core.catalog_search(a["query"], size=5)["items"]
        if not hits:
            return {"found": False}
        return core.solution_plan(hits[0]["folder"]) | {"otherMatches": [h["name"] for h in hits[1:]]}
    raise ValueError(f"Unknown tool {name}")


@router.post("/mcp", tags=["mcp"])
async def mcp(request: Request, user: User = Depends(current_user)):
    try:
        msg = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}, 400)
    batch = msg if isinstance(msg, list) else [msg]
    out = [r for r in (_handle(request.app.state.core, user, m) for m in batch) if r is not None]
    if not out:
        return Response(status_code=202)
    return JSONResponse(out if isinstance(msg, list) else out[0])


@router.get("/mcp", tags=["mcp"])
def mcp_get():
    return Response(status_code=405, headers={"Allow": "POST"})


def _handle(core, user: User, m: dict) -> dict | None:
    mid, method, params = m.get("id"), m.get("method"), m.get("params") or {}
    if mid is None:  # notification
        return None
    ok = lambda result: {"jsonrpc": "2.0", "id": mid, "result": result}  # noqa: E731
    err = lambda code, text: {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": text}}  # noqa: E731
    if method == "initialize":
        return ok({"protocolVersion": params.get("protocolVersion", PROTOCOL),
                   "capabilities": {"tools": {"listChanged": False}},
                   "serverInfo": {"name": "lakehunt", "title": settings.product_name, "version": settings.version},
                   "instructions": INSTRUCTIONS})
    if method == "ping":
        return ok({})
    if method == "tools/list":
        tools = [{k: t[k] for k in ("name", "description", "inputSchema")} for t in TOOLS if user.level >= RANK[t["role"]]]
        return ok({"tools": tools})
    if method == "tools/call":
        t = next((x for x in TOOLS if x["name"] == params.get("name")), None)
        if not t:
            return err(-32602, "Unknown tool")
        if user.level < RANK[t["role"]]:
            return ok({"content": [{"type": "text", "text": f"Requires the {t['role']} role"}], "isError": True})
        try:
            res = _call(core, user, t["name"], params.get("arguments") or {})
            core.store.audit(user.name, f"mcp.{t['name']}", params.get("arguments") or {})
            text = json.dumps(res, default=str)
            if len(text) > 200000:
                text = text[:200000] + "...(truncated)"
            return ok({"content": [{"type": "text", "text": text}], "structuredContent": {"result": res} if len(text) < 200000 else None,
                       "isError": False})
        except Exception as e:  # noqa: BLE001
            return ok({"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True})
    return err(-32601, f"Method not found: {method}")
