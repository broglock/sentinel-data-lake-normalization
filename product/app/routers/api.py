"""REST API, version 1. Every screen in the web UI uses these endpoints, and so can scripts,
pipelines and agents (OpenAPI at /api/docs)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse, Response
import yaml

from app.auth import User, current_user, require
from app.config import settings
from app.core import STAGE_LABELS, STAGES

router = APIRouter(prefix="/api/v1")


def core(request: Request):
    return request.app.state.core


def _err(e: Exception):
    if isinstance(e, KeyError):
        raise HTTPException(404, f"Not found: {e}")
    if isinstance(e, ValueError):
        raise HTTPException(400, str(e))
    raise HTTPException(502, str(e))


# ------------------------------------------------------------------ identity and overview
@router.get("/me", tags=["general"])
def me(user: User = Depends(current_user)):
    return {"name": user.name, "role": user.role, "roles": user.roles, "mode": settings.mode,
            "product": settings.product_name, "version": settings.version,
            "workspace": settings.workspace_name or "demo-workspace", "liveMissing": settings.live_ready}


@router.get("/overview", tags=["general"])
def overview(c=Depends(core), _: User = Depends(require("viewer"))):
    return c.overview()


# ------------------------------------------------------------------ connector catalog
@router.get("/catalog/solutions", tags=["catalog"])
def catalog(q: str = "", asim: str = "", kind: str = "", page: int = 1, size: int = Query(50, le=200),
            c=Depends(core), _: User = Depends(require("viewer"))):
    return c.catalog_search(q, asim, kind, page, size)


@router.get("/catalog/solutions/{folder}/plan", tags=["catalog"])
def solution_plan(folder: str, c=Depends(core), _: User = Depends(require("viewer"))):
    try:
        return c.solution_plan(folder)
    except Exception as e:  # noqa: BLE001
        _err(e)


@router.get("/catalog/tables/{table}", tags=["catalog"])
def catalog_table(table: str, c=Depends(core), _: User = Depends(require("viewer"))):
    return {"table": table, "schema": c.catalog["schemas"].get(table), "solutions": c.solutions_by_table.get(table, []),
            "asimParsers": c.parsers_by_table.get(table, [])}


@router.post("/deployments", tags=["catalog"])
def request_deployment(body: dict = Body(..., examples=[{"solutions": [{"name": "Okta Single Sign-On"}],
                                                       "tables": [{"name": "OktaV2_CL", "plan": "Lake",
                                                                   "retentionDays": 365, "columns": []}]}]),
                       c=Depends(core), user: User = Depends(require("analyst"))):
    """Request solution installs and table creation. Nothing changes in the tenant until an Admin approves."""
    if not body.get("solutions") and not body.get("tables"):
        raise HTTPException(400, "Nothing to deploy")
    for t in body.get("tables", []):
        if t.get("plan") not in ("Analytics", "Basic", "Lake", "Auxiliary"):
            raise HTTPException(400, f"Plan for {t.get('name')} must be Analytics, Basic or Lake")
        if t["plan"] == "Lake":
            t["plan"] = "Auxiliary"  # the tables API names the lake-only plan Auxiliary
    names = ", ".join([s["name"] for s in body.get("solutions", [])] + [t["name"] for t in body.get("tables", [])])
    aid = c.store.request_approval("deployment", f"Deploy: {names}"[:200], body, user.name)
    c.store.audit(user.name, "deployment.request", {"approval": aid})
    return {"approval": aid, "status": "pending"}


@router.get("/solutions/installed", tags=["catalog"])
def installed(c=Depends(core), _: User = Depends(require("viewer"))):
    return c._installed()


# ------------------------------------------------------------------ sources (tables) and onboarding
@router.get("/tables", tags=["sources"])
def tables(c=Depends(core), _: User = Depends(require("viewer"))):
    return {"tables": c.table_overview(), "stages": STAGES, "labels": STAGE_LABELS}


@router.get("/tables/{table}/proposals", tags=["sources"])
def proposals(table: str, preset: str | None = None, c=Depends(core), _: User = Depends(require("viewer"))):
    try:
        return c.proposals(table, preset)
    except Exception as e:  # noqa: BLE001
        _err(e)


@router.post("/tables/{table}/preview", tags=["sources"])
def preview(table: str, body: dict = Body(...), c=Depends(core), _: User = Depends(require("analyst"))):
    """Body: {"decisions": {...}} from the review screen, or {"group": {...}} for a raw registry entry."""
    try:
        return c.preview(table, body.get("decisions"), body.get("group"))
    except Exception as e:  # noqa: BLE001
        _err(e)


@router.get("/tables/{table}/sample", tags=["sources"])
def sample(table: str, n: int = Query(20, le=200), c=Depends(core), _: User = Depends(require("analyst"))):
    from app.core import _j
    return [_j(r) for r in c.p.sample(table, n)]


@router.get("/onboarding/{table}", tags=["sources"])
def onboarding(table: str, c=Depends(core), _: User = Depends(require("viewer"))):
    return {"stage": c.store.stage(table), "history": c.store.stage_history(table)}


@router.post("/onboarding/{table}/stage", tags=["sources"])
def set_stage(table: str, body: dict = Body(..., examples=[{"stage": "deployed", "note": "jobs created"}]),
              c=Depends(core), user: User = Depends(require("analyst"))):
    try:
        return c.advance(table, body["stage"], user.name, body.get("note", ""))
    except Exception as e:  # noqa: BLE001
        _err(e)


@router.post("/asim/expand", tags=["sources"])
def expand(body: dict = Body(..., examples=[{"parser": "ASimAuthenticationAWSCloudTrail"}]),
           c=Depends(core), _: User = Depends(require("analyst"))):
    """Expand a Microsoft ASIM parser into lake-safe KQL (by catalog name, or pass its YAML as `yaml`)."""
    try:
        return c.expand_parser(body.get("parser"), body.get("yaml"))
    except Exception as e:  # noqa: BLE001
        _err(e)


# ------------------------------------------------------------------ registry
@router.get("/registry", tags=["registry"])
def registry(status: str | None = None, c=Depends(core), _: User = Depends(require("viewer"))):
    return c.store.registry(status)


@router.get("/registry/export", tags=["registry"], response_class=PlainTextResponse)
def registry_export(c=Depends(core), _: User = Depends(require("viewer"))):
    return yaml.safe_dump({"version": 1, "groups": c.live_groups()}, sort_keys=False)


@router.get("/registry/{gid:path}/history", tags=["registry"])
def registry_history(gid: str, c=Depends(core), _: User = Depends(require("viewer"))):
    return c.store.registry_history(gid)


@router.get("/registry/{gid:path}", tags=["registry"])
def registry_get(gid: str, c=Depends(core), _: User = Depends(require("viewer"))):
    r = c.store.registry_get(gid)
    if not r:
        raise HTTPException(404, "Not found")
    return r


@router.put("/registry", tags=["registry"])
def registry_put(body: dict = Body(...), c=Depends(core), user: User = Depends(require("analyst"))):
    """Save a draft registry group (body = {"group": {...}, "note": "..."})."""
    try:
        return c.save_draft(body["group"], user.name, body.get("note", ""))
    except Exception as e:  # noqa: BLE001
        _err(e)


@router.post("/registry/from-decisions/{table}", tags=["registry"])
def registry_from_decisions(table: str, body: dict = Body(...), c=Depends(core), user: User = Depends(require("analyst"))):
    """Build a group from review-screen decisions, save it as a draft and optionally submit it."""
    try:
        from app.engine import guide
        rows = c.p.sample(table, 1)
        g = guide.build_group(table, body["decisions"], list(rows[0].keys()) if rows else [])
        rec = c.save_draft(g, user.name, body.get("note", "built in field review"))
        if body.get("submit"):
            rec["approval"] = c.submit(g["id"], user.name)["approval"]
        return rec
    except Exception as e:  # noqa: BLE001
        _err(e)


@router.post("/registry/{gid:path}/exclude", tags=["registry"])
def registry_exclude(gid: str, body: dict = Body(..., examples=[{"text": "keepalive"}]), c=Depends(core),
                     user: User = Depends(require("analyst"))):
    """Mark lines containing `text` as noise for a text source (creates a draft and an approval request)."""
    try:
        return c.exclude_noise(gid, body["text"], user.name)
    except Exception as e:  # noqa: BLE001
        _err(e)


@router.post("/registry/{gid:path}/submit", tags=["registry"])
def registry_submit(gid: str, c=Depends(core), user: User = Depends(require("analyst"))):
    try:
        return c.submit(gid, user.name)
    except Exception as e:  # noqa: BLE001
        _err(e)


@router.post("/registry/{gid:path}/retire", tags=["registry"])
def registry_retire(gid: str, c=Depends(core), user: User = Depends(require("admin"))):
    r = c.store.registry_set_status(gid, "retired", user.name, "retired")
    if not r:
        raise HTTPException(404, "Not found")
    c.reindex()
    c.store.audit(user.name, "registry.retire", {"id": gid})
    return r


# ------------------------------------------------------------------ approvals
@router.get("/approvals", tags=["approvals"])
def approvals(status: str | None = None, c=Depends(core), _: User = Depends(require("viewer"))):
    return c.store.approvals(status)


@router.post("/approvals/{aid}/approve", tags=["approvals"])
def approve(aid: int, c=Depends(core), user: User = Depends(require("admin"))):
    try:
        return c.execute(aid, user.name)
    except Exception as e:  # noqa: BLE001
        _err(e)


@router.post("/approvals/{aid}/reject", tags=["approvals"])
def reject(aid: int, body: dict = Body(default={}), c=Depends(core), user: User = Depends(require("admin"))):
    a = c.store.approval(aid)
    if not a or a["status"] != "pending":
        raise HTTPException(400, "Approval is not pending")
    if a["kind"] == "registry":
        c.store.registry_set_status(a["payload"]["id"], "draft", user.name, "rejected: " + body.get("reason", ""))
        c.store.set_stage(a["payload"]["group"]["table"], "in_review", user.name, "registry change rejected")
    c.store.audit(user.name, "approval.reject", {"id": aid, "reason": body.get("reason", "")})
    return c.store.decide(aid, "rejected", user.name, {"reason": body.get("reason", "")})


# ------------------------------------------------------------------ build and deploy
@router.get("/build", tags=["deploy"])
def build(c=Depends(core), _: User = Depends(require("viewer"))):
    b = c.build()
    b["files"] = {k: v for k, v in b["files"].items() if not k.startswith("notebook/0")}
    return b


@router.get("/build/bundle.zip", tags=["deploy"])
def bundle(c=Depends(core), user: User = Depends(require("analyst"))):
    c.store.audit(user.name, "build.download", "")
    return Response(c.bundle(), media_type="application/zip",
                    headers={"Content-Disposition": "attachment; filename=lakehunt-deploy.zip"})


@router.post("/index/run", tags=["deploy"])
def run_index(c=Depends(core), user: User = Depends(require("analyst"))):
    """Demo mode: re-run the index now. Live mode: reports that the lake jobs build the index."""
    c.store.audit(user.name, "index.run", "")
    return c.reindex()


# ------------------------------------------------------------------ coverage and validation
@router.get("/coverage", tags=["validation"])
def coverage(c=Depends(core), _: User = Depends(require("viewer"))):
    return c.coverage()


@router.get("/coverage/{gid:path}/history", tags=["validation"])
def coverage_history(gid: str, c=Depends(core), _: User = Depends(require("viewer"))):
    g = next((x for x in c.index_groups() if x["id"] == gid), None)
    if not g:
        raise HTTPException(404, "Not found")
    return c.p.history(g)


@router.post("/validation/{gid:path}/run", tags=["validation"])
def validate(gid: str, body: dict = Body(default={}), c=Depends(core), user: User = Depends(require("analyst"))):
    """Runs the four checks. Body: {"canaryValue": "...", "handCheck": true|false}."""
    try:
        return c.validate(gid, user.name, body.get("canaryValue"), body.get("handCheck"))
    except Exception as e:  # noqa: BLE001
        _err(e)


@router.get("/validation", tags=["validation"])
def validations(group: str | None = None, c=Depends(core), _: User = Depends(require("viewer"))):
    return c.store.validations(group)


# ------------------------------------------------------------------ hunting
def _hunt(c, tool: str, **p: Any):
    try:
        return c.p.hunt(tool, **p)
    except Exception as e:  # noqa: BLE001
        _err(e)


@router.get("/hunt/value", tags=["hunt"])
def hunt_value(v: str, days: float = 7, c=Depends(core), _: User = Depends(require("viewer"))):
    return {"sources": _hunt(c, "hunt_value", value=v, days=days), "related": _hunt(c, "related", value=v, days=days),
            "timeline": _hunt(c, "timeline", value=v, days=days)}


@router.get("/hunt/entity", tags=["hunt"])
def hunt_entity(type: str, v: str, role: str = "*", days: float = 7, c=Depends(core), _: User = Depends(require("viewer"))):
    return _hunt(c, "hunt_entity", entity_type=type, value=v, role=role, days=days)


@router.get("/hunt/auth", tags=["hunt"])
def hunt_auth(user: str, result: str = "*", days: float = 7, c=Depends(core), _: User = Depends(require("viewer"))):
    return _hunt(c, "auth_events", user=user, result=result, days=days)


@router.get("/hunt/network", tags=["hunt"])
def hunt_network(ip: str, days: float = 7, c=Depends(core), _: User = Depends(require("viewer"))):
    return _hunt(c, "network_events", ip=ip, days=days)


@router.get("/hunt/search", tags=["hunt"])
def hunt_search(table: str, text: str, hours: float = 24, c=Depends(core), _: User = Depends(require("analyst"))):
    return _hunt(c, "search_raw", table=table, text=text, hours=hours)


@router.get("/hunt/pivot", tags=["hunt"])
def hunt_pivot(table: str, time: str, value: str, key: str = "", group: str = "", until: str = "", c=Depends(core),
               _: User = Depends(require("viewer"))):
    g = next((x for x in c.index_groups() if x["id"] == group), None) if group else None
    from app.kit.generate import complete_group
    try:
        return c.p.pivot(table, time, value, key, complete_group(g) if g else None, until)
    except Exception as e:  # noqa: BLE001
        _err(e)


# ------------------------------------------------------------------ admin
@router.get("/audit", tags=["admin"])
def audit(limit: int = 200, c=Depends(core), _: User = Depends(require("admin"))):
    return c.store.audit_log(limit)


@router.get("/settings", tags=["admin"])
def get_settings(_: User = Depends(require("viewer"))):
    keys = ["mode", "auth_mode", "subscription_id", "resource_group", "workspace_name", "workspace_id",
            "workspace_location", "tables_api_version", "content_api_version", "lake_query_url", "lake_scope",
            "min_extraction", "min_template_match", "kql_job_limit", "kql_job_soft_limit"]
    return {k: getattr(settings, k) for k in keys} | {"liveMissing": settings.live_ready}
