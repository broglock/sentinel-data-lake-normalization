"""Application state in SQLite: registry entries and their history, onboarding stages,
approvals, validation runs, audit log. The lake holds the data; this holds the workflow."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = """
create table if not exists registry (
  id text primary key, doc text not null, status text not null, version integer not null,
  updated_by text, updated_at text);
create table if not exists registry_history (
  id text, version integer, doc text, status text, by text, at text, note text);
create table if not exists onboarding (
  tbl text primary key, stage text not null, info text, updated_at text);
create table if not exists onboarding_history (tbl text, stage text, by text, at text, note text);
create table if not exists approvals (
  id integer primary key autoincrement, kind text, title text, payload text, status text,
  requested_by text, requested_at text, decided_by text, decided_at text, result text);
create table if not exists validations (
  id integer primary key autoincrement, group_id text, run_at text, by text, passed integer, checks text);
create table if not exists audit (at text, by text, action text, detail text);
create table if not exists kv (k text primary key, v text);
"""


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.db.executescript(SCHEMA)
            self.db.commit()

    def _x(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self.lock:
            cur = self.db.execute(sql, args)
            rows = cur.fetchall()
            self.db.commit()
            return rows

    # ------------------------------------------------------------ audit
    def audit(self, by: str, action: str, detail: Any = "") -> None:
        self._x("insert into audit values (?,?,?,?)", (now(), by, action,
                                                       detail if isinstance(detail, str) else json.dumps(detail)))

    def audit_log(self, limit: int = 200) -> list[dict]:
        return [dict(r) for r in self._x("select * from audit order by at desc limit ?", (limit,))]

    # ------------------------------------------------------------ registry
    def registry(self, status: str | None = None) -> list[dict]:
        sql, args = "select * from registry", ()
        if status:
            sql, args = sql + " where status = ?", (status,)
        out = []
        for r in self._x(sql + " order by id", args):
            out.append({"id": r["id"], "status": r["status"], "version": r["version"], "updated_by": r["updated_by"],
                        "updated_at": r["updated_at"], "group": json.loads(r["doc"])})
        return out

    def registry_get(self, gid: str) -> dict | None:
        r = self._x("select * from registry where id = ?", (gid,))
        if not r:
            return None
        r = r[0]
        return {"id": r["id"], "status": r["status"], "version": r["version"], "updated_by": r["updated_by"],
                "updated_at": r["updated_at"], "group": json.loads(r["doc"])}

    def registry_put(self, group: dict, status: str, by: str, note: str = "") -> dict:
        cur = self.registry_get(group["id"])
        ver = (cur["version"] + 1) if cur else 1
        doc = json.dumps(group)
        self._x("insert or replace into registry values (?,?,?,?,?,?)", (group["id"], doc, status, ver, by, now()))
        self._x("insert into registry_history values (?,?,?,?,?,?,?)", (group["id"], ver, doc, status, by, now(), note))
        return self.registry_get(group["id"])

    def registry_set_status(self, gid: str, status: str, by: str, note: str = "") -> dict | None:
        cur = self.registry_get(gid)
        if not cur:
            return None
        return self.registry_put(cur["group"], status, by, note)

    def registry_history(self, gid: str) -> list[dict]:
        return [dict(r) | {"doc": json.loads(r["doc"])} for r in
                self._x("select * from registry_history where id = ? order by version desc", (gid,))]

    # ------------------------------------------------------------ onboarding
    def stage(self, tbl: str) -> dict | None:
        r = self._x("select * from onboarding where tbl = ?", (tbl,))
        return {"table": r[0]["tbl"], "stage": r[0]["stage"], "info": json.loads(r[0]["info"] or "{}"),
                "updated_at": r[0]["updated_at"]} if r else None

    def stages(self) -> dict[str, dict]:
        return {r["tbl"]: {"table": r["tbl"], "stage": r["stage"], "info": json.loads(r["info"] or "{}"),
                           "updated_at": r["updated_at"]} for r in self._x("select * from onboarding")}

    def set_stage(self, tbl: str, stage: str, by: str, note: str = "", info: dict | None = None) -> None:
        cur = self.stage(tbl)
        merged = {**(cur["info"] if cur else {}), **(info or {})}
        self._x("insert or replace into onboarding values (?,?,?,?)", (tbl, stage, json.dumps(merged), now()))
        self._x("insert into onboarding_history values (?,?,?,?,?)", (tbl, stage, by, now(), note))

    def stage_history(self, tbl: str) -> list[dict]:
        return [dict(r) for r in self._x("select * from onboarding_history where tbl = ? order by at", (tbl,))]

    # ------------------------------------------------------------ approvals
    def request_approval(self, kind: str, title: str, payload: dict, by: str) -> int:
        with self.lock:
            cur = self.db.execute("insert into approvals (kind, title, payload, status, requested_by, requested_at) "
                                  "values (?,?,?,?,?,?)", (kind, title, json.dumps(payload), "pending", by, now()))
            self.db.commit()
            return cur.lastrowid

    def approvals(self, status: str | None = None) -> list[dict]:
        sql, args = "select * from approvals", ()
        if status:
            sql, args = sql + " where status = ?", (status,)
        return [self._ap(r) for r in self._x(sql + " order by id desc", args)]

    def approval(self, aid: int) -> dict | None:
        r = self._x("select * from approvals where id = ?", (aid,))
        return self._ap(r[0]) if r else None

    def decide(self, aid: int, status: str, by: str, result: Any = None) -> dict | None:
        self._x("update approvals set status = ?, decided_by = ?, decided_at = ?, result = ? where id = ?",
                (status, by, now(), json.dumps(result), aid))
        return self.approval(aid)

    @staticmethod
    def _ap(r) -> dict:
        d = dict(r)
        d["payload"] = json.loads(d["payload"] or "{}")
        d["result"] = json.loads(d["result"]) if d.get("result") else None
        return d

    # ------------------------------------------------------------ validation
    def add_validation(self, gid: str, by: str, passed: bool, checks: list[dict]) -> int:
        with self.lock:
            cur = self.db.execute("insert into validations (group_id, run_at, by, passed, checks) values (?,?,?,?,?)",
                                  (gid, now(), by, int(passed), json.dumps(checks)))
            self.db.commit()
            return cur.lastrowid

    def validations(self, gid: str | None = None, limit: int = 100) -> list[dict]:
        sql, args = "select * from validations", ()
        if gid:
            sql, args = sql + " where group_id = ?", (gid,)
        rows = self._x(sql + " order by id desc limit ?", args + (limit,))
        return [dict(r) | {"checks": json.loads(r["checks"]), "passed": bool(r["passed"])} for r in rows]

    # ------------------------------------------------------------ kv
    def get(self, k: str, default: Any = None) -> Any:
        r = self._x("select v from kv where k = ?", (k,))
        return json.loads(r[0]["v"]) if r else default

    def set(self, k: str, v: Any) -> None:
        self._x("insert or replace into kv values (?,?)", (k, json.dumps(v)))
