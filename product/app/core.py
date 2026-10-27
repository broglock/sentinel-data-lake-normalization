"""Application services: registry, onboarding workflow, proposals, preview, build, validation,
approvals. Routers call these; providers do the data access."""
from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import datetime, timezone
from typing import Any

import httpx
import yaml

from app.config import APP_DIR, settings
from app.engine import guide, miner
from app.engine.indexer import index_parts
from app.kit import asim_expand
from app.kit.generate import (ASIM_OUTPUT_FIELDS, ENTITY_COLUMNS, EVENT_COLUMNS, EVENT_OCC_COLUMNS, build_entity_job, build_entity_query,
                              build_event_job, build_event_query, complete_group, engine_of, notebook_config,
                              plan_jobs, slug)
from app.providers.base import Provider
from app.store import Store

STAGES = ["detected", "proposed", "in_review", "registry", "deployed", "validating", "live"]
STAGE_LABELS = {"detected": "New table lands", "proposed": "Proposals ready", "in_review": "Mapping review",
                "registry": "Registry change", "deployed": "Deployed", "validating": "Validating",
                "live": "Live", "failed": "Back to review"}
INTERNAL_TABLES = ("HuntEntity", "HuntEvent", "HuntCoverage", "FieldInventory", "TemplateCandidates", "Usage",
                   "Heartbeat", "Operation")


class Core:
    def __init__(self, store: Store, provider: Provider):
        self.store = store
        self.p = provider
        self.vocab = yaml.safe_load(open(APP_DIR / "kit" / "vocab.yaml", encoding="utf-8"))
        self.catalog = json.load(open(APP_DIR / "data" / "catalog.json", encoding="utf-8"))
        self.parsers_by_table: dict[str, list[dict]] = {}
        for p in self.catalog["parsers"]:
            for t in p["tables"]:
                self.parsers_by_table.setdefault(t, []).append(p)
        self.solutions_by_table: dict[str, list[str]] = {}
        for s in self.catalog["solutions"]:
            for t in s["tables"]:
                self.solutions_by_table.setdefault(t, []).append(s["name"])

    # ================================================================ startup
    def bootstrap(self) -> None:
        if self.p.mode == "demo" and not self.store.registry():
            reg = yaml.safe_load(open(APP_DIR / "demo" / "demo_registry.yaml", encoding="utf-8"))
            for g in reg["groups"]:
                self.store.registry_put(g, "live", "system", "demo registry")
            for t in {g["table"] for g in reg["groups"]}:
                for st in ("detected", "proposed", "in_review", "registry", "deployed", "validating", "live"):
                    self.store.set_stage(t, st, "system", "demo history")
            self.store.set_stage("BadgeReader_CL", "detected", "system", "first rows seen")
            self.store.set_stage("BadgeReader_CL", "proposed", "system", "notebook 01 proposals ready")
            self.store.audit("system", "demo.seed", "Seeded demo registry and onboarding history")
        self.reindex()

    def reindex(self) -> dict:
        return self.p.reindex(self.index_groups(), self.vocab)

    # ================================================================ registry
    def live_groups(self) -> list[dict]:
        return [r["group"] for r in self.store.registry() if r["status"] == "live"]

    def index_groups(self) -> list[dict]:
        """Live registry groups plus a classifier-only group for every table nothing maps yet,
        so a new source is searchable from its first indexing run."""
        groups = self.live_groups()
        mapped = {g["table"] for g in groups}
        for t in self.p.tables():
            if t["name"] in mapped or t["name"].startswith(INTERNAL_TABLES):
                continue
            auto = self.auto_group(t)
            if auto:
                groups.append(auto)
        return groups

    def auto_group(self, t: dict) -> dict | None:
        cols = [c["name"] for c in t.get("columns", [])]
        text = next((c for c in miner.TEXT_COLUMNS if c in cols), None)
        if not text:
            return None
        return {"id": f"{t['name']}:auto", "table": t["name"], "filter": f"isnotempty({text})",
                "spark_filter": f"{text} IS NOT NULL", "vendor": "", "product": "", "schema": "",
                "status": "proposed", "layer": "classifier", "record_key_fields": [text], "text_column": text,
                "templates": [], "tier": 2, "auto": True}

    def validate_group(self, g: dict) -> list[str]:
        errs = []
        if not re.match(r"^[A-Za-z0-9_:./ -]{3,80}$", g.get("id", "")):
            errs.append("id: 3 to 80 letters, digits or : . / _ -")
        if not re.match(r"^[A-Za-z][A-Za-z0-9_]{1,62}$", g.get("table", "")):
            errs.append("table: not a valid table name")
        try:
            cg = complete_group(g)
            build_entity_query(cg, {}, self.vocab)
            build_event_query(cg, {}, self.vocab)
        except Exception as e:  # noqa: BLE001
            errs.append(f"generator: {e}")
        for t in g.get("templates") or []:
            try:
                re.compile(t["regex"])
            except re.error as e:
                errs.append(f"template {t.get('id')}: {e}")
        return errs

    def save_draft(self, g: dict, user: str, note: str = "") -> dict:
        errs = self.validate_group(g)
        if errs:
            raise ValueError("; ".join(errs))
        cur = self.store.registry_get(g["id"])
        rec = self.store.registry_put(g, "draft" if not cur or cur["status"] != "live" else "draft", user, note or "draft saved")
        self.store.set_stage(g["table"], "in_review", user, f"draft {g['id']} saved")
        self.store.audit(user, "registry.draft", {"id": g["id"]})
        return rec

    def submit(self, gid: str, user: str) -> dict:
        rec = self.store.registry_get(gid)
        if not rec:
            raise KeyError(gid)
        self.store.registry_set_status(gid, "pending", user, "submitted for approval")
        aid = self.store.request_approval("registry", f"Registry change: {gid}", {"id": gid, "group": rec["group"]}, user)
        self.store.set_stage(rec["group"]["table"], "registry", user, f"approval #{aid} requested")
        self.store.audit(user, "registry.submit", {"id": gid, "approval": aid})
        return {"approval": aid}

    # ================================================================ tables and onboarding
    def table_overview(self) -> list[dict]:
        tables = self.p.tables()
        groups = self.store.registry()
        cov = {c["SourceGroup"]: c for c in self.coverage()}
        stages = self.store.stages()
        out = []
        for t in tables:
            if t["name"].startswith(INTERNAL_TABLES):
                continue
            gs = [r for r in groups if r["group"]["table"] == t["name"]]
            live = [r for r in gs if r["status"] == "live"]
            layers = sorted({r["group"].get("layer", "registry") for r in live})
            covs = [cov[r["id"]] for r in live if r["id"] in cov]
            auto = cov.get(f"{t['name']}:auto")
            st = stages.get(t["name"])
            parsers = self.parsers_by_table.get(t["name"], [])
            out.append({
                "name": t["name"], "plan": t.get("plan"), "rows7d": t.get("rows7d"), "mb7d": t.get("mb7d"),
                "lastSeen": t.get("lastSeen"), "groups": [{"id": r["id"], "status": r["status"]} for r in gs],
                "layers": layers or (["classifier"] if auto else []),
                "tier": 1 if live else (2 if auto else None),
                "extraction": round(sum(c["ExtractionRate"] for c in covs) / len(covs), 4) if covs else
                (auto["ExtractionRate"] if auto else None),
                "status": ("ok" if covs and all(c["Status"] == "ok" for c in covs) else
                           "review" if covs else "classifier-only" if auto else "unmapped"),
                "stage": st["stage"] if st else ("live" if live else "detected"),
                "asimParsers": sorted({p["builtIn"] or p["parser"] for p in parsers})[:12],
                "asimParserCount": len(parsers),
                "solutions": self.solutions_by_table.get(t["name"], [])[:5],
            })
        return out

    def advance(self, table: str, stage: str, user: str, note: str = "") -> dict:
        if stage not in STAGES + ["failed"]:
            raise ValueError("unknown stage")
        self.store.set_stage(table, stage, user, note)
        self.store.audit(user, "onboarding.stage", {"table": table, "stage": stage, "note": note})
        return self.store.stage(table)

    # ================================================================ proposals and preview
    def suggest_preset(self, table: str, inv: list[dict]) -> str:
        schemas = {p["schema"] for p in self.parsers_by_table.get(table, [])}
        if "Authentication" in schemas and len(schemas) == 1:
            return "authentication"
        if "NetworkSession" in schemas and len(schemas) == 1:
            return "network"
        names = " ".join(i["field"].lower() for i in inv) + " " + table.lower()
        samples = " ".join(" ".join(i.get("samples", [])) for i in inv).lower()
        if re.search(r"badge|door|holder", names + samples):
            return "physical"
        if re.search(r"login|logon|signin|auth|session", names + samples):
            return "authentication"
        if re.search(r"dstport|destinationport|dport|bytes|deviceaction", names):
            return "network"
        if re.search(r"url|useragent|http", names):
            return "web"
        return "other"

    def proposals(self, table: str, preset: str | None = None) -> dict:
        rows = self.p.sample(table, 500)
        inv = miner.inventory(table, rows, self.vocab)
        tpls = miner.mine_templates(table, rows)
        preset = preset or self.suggest_preset(table, inv)
        cards = [guide.recommend(f, preset, inv) for f in inv]
        # result value pickers
        for c in cards:
            if c["decision"] == "result":
                getter = self._getter(c["field"], c["kind"])
                c["values"] = guide.result_values(rows, getter, self.vocab)
            if c["decision"] == "event_type":
                getter = self._getter(c["field"], c["kind"])
                c["values"] = [{"value": v["value"], "rows": v["rows"]} for v in guide.result_values(rows, getter, self.vocab)]
        text_col = next((c for c in miner.TEXT_COLUMNS if rows and c in rows[0]), None)
        kv_share = sum(1 for c in cards if c["kind"] == "kv")
        order = {"high": 0, "medium": 1, "low": 2, "none": 3}
        cards.sort(key=lambda c: ({"entity": 0, "result": 1, "event_type": 2, "record_key": 3, "field": 4, "skip": 5}[c["decision"]],
                                  order.get(c.get("confidence", "none"), 3), -c["fillRate"]))
        parsers = self.parsers_by_table.get(table, [])
        return {
            "table": table, "rows": len(rows), "preset": preset,
            "presets": [{"value": k, **v} for k, v in guide.PRESETS.items()],
            "entityChoices": guide.ENTITY_CHOICES, "roleChoices": guide.ROLE_CHOICES,
            "asimByEntityRole": {f"{k[0]}:{k[1]}": v for k, v in guide.ASIM_BY_ENTITY_ROLE.items()},
            "asimFields": [c for c, _ in EVENT_OCC_COLUMNS if c not in ("EventStartTime", "SourceRecordKey", "SourceTable",
                                                                   "SourceGroup", "MappingTier")],
            "cards": cards, "textColumn": text_col, "kvSource": kv_share > 0,
            "templates": [guide.template_card(t, preset) for t in tpls] if text_col and not kv_share else [],
            "asimParsers": parsers[:20], "existing": [r for r in self.store.registry() if r["group"]["table"] == table],
            "path": ("asim" if parsers else "kv" if kv_share else "templates" if text_col else "fields"),
            "pathHelp": self._path_help(parsers, kv_share, text_col),
            "columns": list(rows[0].keys()) if rows else [],
        }

    def _path_help(self, parsers, kv, text) -> str:
        if parsers:
            names = ", ".join(sorted({p["builtIn"] or p["parser"] for p in parsers})[:3])
            return (f"Microsoft ships ASIM parsers that read this table ({names}). Expand the parser into lake KQL, "
                    "or confirm the field choices below, which follow the same ASIM names.")
        if kv:
            return "The text is key=value pairs. Pick what each key means; the app writes the templates for you."
        if text:
            return "Free text. Each common message shape below is a template: name its slots and set its outcome."
        return "Structured columns. Confirm what each field holds; ASIM names follow from your choices."

    @staticmethod
    def _getter(field: str, kind: str):
        if kind == "column":
            return lambda r: "" if r.get(field) is None else str(r.get(field))
        head, rest = field.split(".", 1)
        if kind == "json":
            def g(r):
                v = r.get(head)
                try:
                    v = json.loads(v) if isinstance(v, str) else v
                    for p in rest.split("."):
                        v = v.get(p) if isinstance(v, dict) else None
                    return "" if v is None else str(v)
                except Exception:  # noqa: BLE001
                    return ""
            return g
        rx = re.compile(r"(?:^|[\s;|,])" + re.escape(rest) + r"=(\"[^\"]*\"|[^\s;|,]*)")
        return lambda r: (m.group(1).strip('"') if (m := rx.search(str(r.get(head) or ""))) else "")

    def preview(self, table: str, decisions: dict | None = None, group: dict | None = None) -> dict:
        rows = self.p.sample(table, 500)
        if group is None:
            group = guide.build_group(table, decisions or {}, list(rows[0].keys()) if rows else [])
        errs = self.validate_group(group)
        if errs:
            return {"group": group, "errors": errs}
        parts = index_parts(rows, group, self.vocab)
        ents, evs = parts["occ"], parts["event"]
        from app.engine.coverage import group_coverage
        c = group_coverage(group, parts["entity"], settings.min_extraction, settings.min_template_match)
        keys = []
        for e in ents:
            if e["SourceRecordKey"] not in keys:
                keys.append(e["SourceRecordKey"])
        sample_keys = keys[:8]
        by_key = {}
        for r in parts["base"]:
            if r["_SourceRecordKey"] in sample_keys:
                by_key[r["_SourceRecordKey"]] = {k: v for k, v in r.items() if not k.startswith("_")}
        pairs = [{"raw": _j(by_key.get(k, {})), "index": [_j(e) for e in ents if e["SourceRecordKey"] == k]} for k in sample_keys]
        cg = complete_group(group)
        return {"group": group, "errors": [], "coverage": c,
                "byEntity": _count(ents, lambda e: f"{e['EntityType']}:{e['Role']}"),
                "byResult": _count(list({e["SourceRecordKey"]: e for e in ents}.values()), lambda e: e["EventResult"] or "(none)"),
                "pairs": pairs, "eventRows": len(evs), "rollupRows": sum(1 for e in parts["entity"] if e["EntityType"] != "_stats"),
                "kql": build_entity_query(cg, {}, self.vocab), "yaml": yaml.safe_dump(group, sort_keys=False)}

    # ================================================================ ASIM parser expansion
    def expand_parser(self, parser: str | None = None, text: str | None = None) -> dict:
        if not text:
            p = next((x for x in self.catalog["parsers"] if parser in (x["parser"], x["builtIn"])), None)
            if not p:
                raise KeyError(parser)
            url = (f"https://raw.githubusercontent.com/Azure/Azure-Sentinel/master/Parsers/ASim{p['schema']}/Parsers/"
                   f"{p['parser']}.yaml")
            r = httpx.get(url, timeout=30)
            r.raise_for_status()
            text = r.text
        doc = yaml.safe_load(text)
        query, params = doc.get("ParserQuery", ""), doc.get("ParserParams", [])
        lake = (asim_expand.params_to_lets(params) + "\n" if params else "") + asim_expand.expand(query)
        remaining = sorted(set(asim_expand.FUNC_CALL.findall(lake)))
        return {"parser": doc.get("ParserName"), "schema": (doc.get("Normalization") or {}).get("Schema"),
                "lakeSafe": not remaining, "remainingCalls": remaining, "query": lake,
                "entityRules": ASIM_OUTPUT_FIELDS}

    # ================================================================ build (deployment artifacts)
    def build(self) -> dict:
        groups = [complete_group(g) for g in self.live_groups() + [g for g in self.index_groups() if g.get("auto")]]
        files, jobs = {}, []
        # approved groups run as KQL jobs, batched per source table: one entity job and at most one event job each
        for name, members in plan_jobs(groups).items():
            ids = [g["id"] for g in members]
            files[f"kql_jobs/{name}.entity.kql"] = build_entity_job(members, {}, self.vocab)
            jobs.append({"name": f"lakehunt-{name}-entity", "groups": ids, "output": settings.entity_table.replace("_SPRK", "_KQL"),
                         "file": f"kql_jobs/{name}.entity.kql"})
            ev = build_event_job(members, {}, self.vocab)
            if ev:
                files[f"kql_jobs/{name}.event.kql"] = ev
                jobs.append({"name": f"lakehunt-{name}-event", "groups": ids, "output": settings.event_table.replace("_SPRK", "_KQL"),
                             "file": f"kql_jobs/{name}.event.kql"})
        cfg = notebook_config(groups, self.vocab)
        files["notebook/notebook_config.json"] = json.dumps(cfg, indent=1, default=str)
        for nb in ("01_inventory_and_mining.py", "02_index_longtail.py", "03_coverage.py"):
            files[f"notebook/{nb}"] = (APP_DIR / "kit" / "notebooks" / nb).read_text(encoding="utf-8")
        files["mcp/tools.yaml"] = (APP_DIR / "kit" / "tools.yaml").read_text(encoding="utf-8")
        files["registry.yaml"] = yaml.safe_dump({"version": 1, "groups": self.live_groups()}, sort_keys=False)
        files["tables.json"] = json.dumps({"HuntEntity": ENTITY_COLUMNS, "HuntEvent": EVENT_COLUMNS}, indent=1)
        files["DEPLOY.md"] = DEPLOY_STEPS.format(n=len(jobs), limit=settings.kql_job_limit)
        nb_groups = [g["id"] for g in groups if engine_of(g) == "notebook"]
        return {"files": files, "jobs": jobs, "notebookGroups": nb_groups,
                "budget": {"kqlJobs": len(jobs), "limit": settings.kql_job_limit, "soft": settings.kql_job_soft_limit,
                           "warning": len(jobs) > settings.kql_job_soft_limit},
                "built": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}

    def bundle(self) -> bytes:
        b = self.build()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for name, content in b["files"].items():
                z.writestr(f"lakehunt-deploy/{name}", content)
            z.writestr("lakehunt-deploy/jobs.json", json.dumps(b["jobs"], indent=1))
        return buf.getvalue()

    # ================================================================ coverage
    def coverage(self) -> list[dict]:
        groups = self.index_groups()
        rows = self.p.coverage(groups)
        meta = {g["id"]: g for g in groups}
        for r in rows:
            g = meta.get(r["SourceGroup"], {})
            r.setdefault("Layer", g.get("layer", ""))
            r["Product"] = g.get("product", "")
            r["Auto"] = bool(g.get("auto"))
        return rows

    # ================================================================ validation (four checks)
    def validate(self, gid: str, user: str, canary_value: str | None = None, hand_check: bool | None = None) -> dict:
        rec = self.store.registry_get(gid)
        if not rec:
            raise KeyError(gid)
        g = rec["group"]
        if self.p.mode == "demo" and rec["status"] != "live":
            raise ValueError("Deploy the group before validating it")
        checks = []
        cov = next((c for c in self.p.coverage([g]) if c.get("SourceGroup") == gid), None)
        if cov:
            ok = cov["ExtractionRate"] >= settings.min_extraction and (
                cov.get("TemplateMatchRate") is None or cov["TemplateMatchRate"] >= settings.min_template_match)
            detail = f"Extraction {cov['ExtractionRate']:.0%} (need {settings.min_extraction:.0%})"
            if cov.get("TemplateMatchRate") is not None:
                detail += f", template match {cov['TemplateMatchRate']:.0%} (need {settings.min_template_match:.0%})"
            checks.append({"check": "coverage", "label": "Coverage numbers", "passed": ok, "detail": detail, "data": cov})
        else:
            checks.append({"check": "coverage", "label": "Coverage numbers", "passed": False, "detail": "No coverage row yet"})
        # hand check: the operator confirms that sampled raw rows and their index rows agree
        # HuntEntity rows are hourly rollups; each carries SampleKeys, so a key leads to one raw row
        rows = self.p.index_rows_for_group(gid, 60)
        sample_keys = list(dict.fromkeys(k for r in rows for k in (r.get("SampleKeys") or [])[:1]))[:5]
        pairs = []
        for k in sample_keys:
            idx = [r for r in rows if k in (r.get("SampleKeys") or [])]
            raw = self.p.pivot(g["table"], idx[0]["FirstSeen"], idx[0]["Value"], k, complete_group(g), idx[0]["LastSeen"])
            pairs.append({"key": k, "index": idx, "raw": raw[:1]})
        checks.append({"check": "hand", "label": "Hand check of sample rows",
                       "passed": bool(hand_check) if hand_check is not None else None,
                       "detail": "Confirmed by " + user if hand_check else "Waiting for the operator to compare the rows",
                       "data": pairs})
        # canary
        c = self.p.canary(g, self.vocab, canary_value)
        if c.get("ok") and self.p.mode == "demo":
            hits = [h for h in self.p.hunt("hunt_value", value=c["value"], days=1) if h["SourceGroup"] == gid]
            c["hits"] = hits
            c["ok"] = bool(hits)
        checks.append({"check": "canary", "label": "Canary event found", "passed": c.get("ok") if not c.get("needsOperator") else None,
                       "detail": (f"Test value {c.get('value')} found through hunt_value" if c.get("ok") else c.get("reason", "Not found")),
                       "data": c})
        # pivot: every sampled index row leads back to exactly one raw row
        piv = [len(p["raw"]) for p in pairs]
        checks.append({"check": "pivot", "label": "Pivot to raw row", "passed": bool(piv) and all(n == 1 for n in piv),
                       "detail": f"{sum(1 for n in piv if n == 1)} of {len(piv)} sampled index rows returned exactly one raw row"})
        decided = [x["passed"] for x in checks]
        passed = all(x is True for x in decided)
        vid = self.store.add_validation(gid, user, passed, checks)
        table = g["table"]
        if passed:
            self.store.set_stage(table, "live", user, f"validation #{vid} passed")
        elif any(x is False for x in decided):
            self.store.set_stage(table, "failed", user, f"validation #{vid} failed")
        else:
            self.store.set_stage(table, "validating", user, f"validation #{vid} waiting for operator checks")
        self.store.audit(user, "validation.run", {"group": gid, "id": vid, "passed": passed})
        return {"id": vid, "group": gid, "passed": passed, "checks": checks}

    # ================================================================ drift (what changed in a source)
    def drift(self, gid: str) -> dict:
        g = next((x for x in self.index_groups() if x["id"] == gid), None)
        if not g:
            raise KeyError(gid)
        from app.engine.indexer import make_filter
        rows = [r for r in self.p.sample(g["table"], 2000) if make_filter(g)(r)]
        cov = next((c for c in self.p.coverage([g]) if c.get("SourceGroup") == gid), None)
        text = g.get("text_column")
        unmatched, missing = [], []
        if text:
            tpls = g.get("templates") or []
            rest = [r for r in rows if not any(re.search(t["regex"], str(r.get(text) or "")) for t in tpls)]
            unmatched = [guide.template_card(t, "other") for t in miner.mine_templates(g["table"], rest, 10)]
        else:
            cols = set(rows[0].keys()) if rows else set()
            for f in g.get("fields", []):
                if "column" in f and f["column"] not in cols:
                    missing.append(f["column"])
        empty = []
        for f in g.get("fields", []):
            if "column" in f and rows:
                fill = sum(1 for r in rows if r.get(f["column"]) not in (None, "", "-")) / len(rows)
                if fill < 0.2:
                    empty.append({"field": f["column"], "fill": round(fill, 3)})
        return {"group": gid, "coverage": cov, "history": self.p.history(g), "sampleRows": len(rows),
                "unmatchedTemplates": unmatched, "missingColumns": missing, "nearlyEmptyFields": empty,
                "summary": ("New message shapes are not matched by any template" if unmatched else
                            "Mapped columns are missing from the table" if missing else
                            "Mapped fields are mostly empty" if empty else "No drift found in the sample")}

    def exclude_noise(self, gid: str, text: str, user: str) -> dict:
        """Operator marks a message shape as noise: a draft with exclude_text, submitted for approval."""
        rec = self.store.registry_get(gid)
        if not rec:
            raise KeyError(gid)
        g = {k: v for k, v in rec["group"].items() if k != "_excluded"}
        g["exclude_text"] = sorted(set((g.get("exclude_text") or []) + [text]))
        self.save_draft(g, user, f"exclude noise: {text}")
        return self.submit(gid, user)

    # ================================================================ approvals
    def execute(self, aid: int, user: str) -> dict:
        a = self.store.approval(aid)
        if not a or a["status"] != "pending":
            raise ValueError("Approval is not pending")
        kind, p = a["kind"], a["payload"]
        try:
            if kind == "registry":
                # an approved mapping moves to the shared KQL job for its table; the notebook stops reading it
                g = {**p["group"], "status": "approved"}
                g.pop("engine", None)
                self.store.registry_put(g, "live", user, f"approved #{aid}")
                result = {"reindex": self.reindex(), "message": "Registry entry is live. In live mode, rebuild and "
                          "redeploy the jobs from the Deploy screen."}
                self.store.set_stage(g["table"], "deployed" if self.p.mode == "demo" else "registry", user, f"approval #{aid}")
            elif kind == "deployment":
                result = {"solutions": [], "tables": []}
                for s in p.get("solutions", []):
                    result["solutions"].append(self.p.install_solution(s))
                for t in p.get("tables", []):
                    result["tables"].append(self.p.create_table(t["name"], t.get("columns", []), t.get("plan", "Analytics"),
                                                                int(t.get("retentionDays", 365))))
                    self.store.set_stage(t["name"], "detected", user, f"created by approval #{aid}")
            else:
                raise ValueError(f"Unknown approval kind {kind}")
        except Exception as e:  # noqa: BLE001
            self.store.decide(aid, "failed", user, {"error": str(e)})
            self.store.audit(user, "approval.failed", {"id": aid, "error": str(e)})
            raise
        self.store.decide(aid, "executed", user, result)
        self.store.audit(user, "approval.executed", {"id": aid, "kind": kind})
        return self.store.approval(aid)

    # ================================================================ catalog
    def catalog_search(self, q: str = "", asim: str = "", kind: str = "", page: int = 1, size: int = 50) -> dict:
        installed = {s["name"] for s in self._installed()}
        ql = q.lower().strip()
        items = []
        for s in self.catalog["solutions"]:
            if not s["connectors"]:
                continue
            if ql and ql not in s["name"].lower() and not any(ql in t.lower() for t in s["tables"]) \
                    and not any(ql in c["title"].lower() for c in s["connectors"]):
                continue
            has_asim = bool(s["asimTables"])
            if asim == "yes" and not has_asim or asim == "no" and has_asim:
                continue
            custom = [t for t in s["tables"] if t.endswith("_CL")]
            if kind == "custom" and not custom or kind == "native" and custom:
                continue
            items.append({"name": s["name"], "folder": s["folder"], "version": s["version"], "author": s["author"],
                          "connectors": len(s["connectors"]), "tables": s["tables"], "asimTables": s["asimTables"],
                          "deprecatedOnly": all(c["deprecated"] for c in s["connectors"]),
                          "installed": s["name"] in installed,
                          "path": "asim" if len(s["asimTables"]) == len(s["tables"]) else
                                  "mixed" if s["asimTables"] else "registry"})
        total = len(items)
        return {"total": total, "page": page, "size": size, "items": items[(page - 1) * size: page * size],
                "stats": self.catalog_stats(), "source": self.catalog["source"], "commit": self.catalog["commit"],
                "built": self.catalog["built"]}

    def catalog_stats(self) -> dict:
        sols = [s for s in self.catalog["solutions"] if s["connectors"]]
        tables = {t for s in sols for t in s["tables"]}
        asim = {t for s in sols for t in s["asimTables"]}
        return {"solutions": len(sols), "connectors": sum(len(s["connectors"]) for s in sols),
                "tables": len(tables), "tablesWithAsim": len(asim), "customTables": sum(1 for t in tables if t.endswith("_CL")),
                "schemas": len(self.catalog["schemas"]), "asimParsers": len(self.catalog["parsers"])}

    def _installed(self) -> list[dict]:
        try:
            return self.p.installed_solutions()
        except Exception:  # noqa: BLE001
            return []

    def solution_plan(self, folder: str) -> dict:
        s = next((x for x in self.catalog["solutions"] if x["folder"] == folder), None)
        if not s:
            raise KeyError(folder)
        existing = {t["name"] for t in self.p.tables()}
        tables = []
        for t in s["tables"]:
            parsers = self.parsers_by_table.get(t, [])
            schema = self.catalog["schemas"].get(t)
            custom = t.endswith("_CL")
            tables.append({
                "name": t, "exists": t in existing, "custom": custom,
                "schemaKnown": bool(schema), "columns": schema or [],
                "createdBy": ("this app (schema from the solution)" if custom and schema else
                              "the connector when it is enabled" if custom else "Microsoft (built-in table)"),
                "recommendedPlan": "Analytics" if parsers and not custom else "Lake",
                "planReason": ("Has an ASIM parser and analytics content; keep in analytics, mirrored to the lake" if parsers and not custom
                               else "Hunting and retention only: data lake tier, indexed by Lake Hunt"),
                "asimParsers": sorted({p["builtIn"] or p["parser"] for p in parsers}),
                "mappingPath": "ASIM logic" if parsers else "Registry rules or templates (review in the app)",
            })
        return {"solution": {k: s[k] for k in ("name", "folder", "version", "author")}, "connectors": s["connectors"],
                "tables": tables, "dependsOn": s.get("dependsOn", []),
                "manualSteps": [
                    "Enter the vendor credentials or agent settings on the connector page in the Defender portal "
                    "(the app never handles vendor secrets).",
                    "For Lake plan tables, confirm the tier under Microsoft Sentinel > Configuration > Tables.",
                    "After first data arrives the table appears under Sources with proposals ready."]}

    # ================================================================ overview
    def overview(self) -> dict:
        tabs = self.table_overview()
        cov = self.coverage()
        pend = self.store.approvals("pending")
        tiers = {"tier1": sum(1 for t in tabs if t["tier"] == 1), "tier2": sum(1 for t in tabs if t["tier"] == 2),
                 "unmapped": sum(1 for t in tabs if t["tier"] is None)}
        stages = {}
        for t in tabs:
            stages[t["stage"]] = stages.get(t["stage"], 0) + 1
        return {"mode": self.p.mode, "tables": len(tabs), **tiers, "stages": stages,
                "groups": len(self.live_groups()), "coverage": cov,
                "statusCounts": _count(cov, lambda c: c["Status"]),
                "pendingApprovals": len(pend), "catalog": self.catalog_stats(),
                "attention": [t for t in tabs if t["status"] in ("review", "classifier-only", "unmapped")
                              or t["stage"] in ("proposed", "in_review", "registry", "validating", "failed")][:12],
                "recentValidations": self.store.validations(limit=8),
                "build": {k: v for k, v in self.build().items() if k != "files"}}


DEPLOY_STEPS = """# Deploying the Lake Hunt index

{n} KQL job queries in kql_jobs/ (tenant limit {limit} enabled jobs).

1. Create the index tables by running each KQL job once with "create new table" (HuntEntity_KQL,
   HuntEvent_KQL), or let the notebook create HuntEntity_SPRK / HuntEvent_SPRK on its first run.
   Keep one naming choice for every job; tables.json lists the columns in order.
2. Defender portal > Microsoft Sentinel > Data lake exploration > Jobs > Create job, one per file in
   jobs.json: paste the query, hourly schedule, stagger start minutes (:05, :10, ...), append to the
   output table named in jobs.json.
3. Notebook jobs (VS Code with the Microsoft Sentinel extension): upload notebook/02_index_longtail.py with
   notebook_config.json pasted into CONFIG_JSON, schedule hourly. Upload 01 (daily) and 03 (daily).
4. Save the queries in mcp/tools.yaml as custom MCP tools, or register them in your MCP server.
5. In this app, set each onboarding source to Deployed, then run Validation after the first run.
"""


def _j(r: dict) -> dict:
    return {k: (v.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z" if isinstance(v, datetime) else v) for k, v in r.items()}


def _count(items, key) -> dict:
    out: dict[str, int] = {}
    for i in items:
        k = key(i)
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))
