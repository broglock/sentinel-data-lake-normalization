"""Pure-Python index engine.

Applies the same registry rules as the generated KQL jobs and the lake notebook
(app/kit/generate.py, app/kit/notebooks/02_index_longtail.py) to rows held in memory.
Used for demo mode, for the live preview in the field review screen, and for tests.
The rules and their order match the Spark engine line for line; tests/test_parity.py
checks the two against the five-source example.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from datetime import datetime
from typing import Any, Iterable

from app.kit.generate import (CLASSIFIER, ENTITY_COLUMNS, EVENT_COLUMNS, OCC_COLUMNS, ROLLUP_KEYS, SAMPLE_KEYS,
                              complete_group, event_templates, slot_asim)

Row = dict[str, Any]


# ---------------------------------------------------------------- field access
def _path_get(obj: Any, parts: list[str]) -> Any:
    for p in parts:
        if isinstance(obj, str):
            try:
                obj = json.loads(obj)
            except ValueError:
                return None
        if not isinstance(obj, dict):
            return None
        obj = obj.get(p)
    return obj


def _s(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (dict, list)):
        return json.dumps(v, separators=(",", ":"))
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return str(v)


def field_value(row: Row, rule: dict) -> str:
    if "column" in rule:
        v = _s(row.get(rule["column"]))
        lab = rule.get("when_label")
        if lab and _s(row.get(lab["column"])) != str(lab["equals"]):
            return ""
        return v
    head, *rest = rule["path"].split(".")
    return _s(_path_get(row.get(head), rest))


def map_value(row: Row, rule: dict) -> str:
    src = field_value(row, rule)
    for k, v in rule["map"].items():
        if src == str(k):
            return str(v)
    return str(rule.get("default", ""))


def result_value(row: Row, group: dict, vocab: dict) -> str:
    rule = group.get("result")
    if not rule:
        return ""
    if "map" in rule:
        return map_value(row, rule)
    v = vocab["result_vocab"][rule.get("vocab", "default")]
    r = field_value(row, rule).strip().lower()
    for outcome in ("Success", "Failure", "Partial"):
        if r in [str(w) for w in v.get(outcome, [])]:
            return outcome
    if v.get("http_status") and re.fullmatch(r"-?\d+", r):
        n = int(r)
        if 100 <= n <= 399:
            return "Success"
        if 400 <= n <= 599:
            return "Failure"
    return "NA"


def event_type_value(row: Row, group: dict) -> str:
    rule = group.get("event_type")
    if not rule:
        return ""
    if "constant" in rule:
        return str(rule["constant"])
    if "map" in rule:
        return map_value(row, rule)
    return field_value(row, rule)


# ---------------------------------------------------------------- record key
def record_key(row: Row, group: dict) -> str:
    g = complete_group(group)
    tc = g.get("time_column", "TimeGenerated")
    if g.get("record_key_path"):
        head, *rest = g["record_key_path"].split(".")
        return _s(_path_get(row.get(head), rest))
    cols = g.get("record_key_fields")
    if not cols:
        raise ValueError(f"group {g['id']}: the Python engine needs record_key_fields or record_key_path")
    t = row.get(tc)
    ts = t.strftime("%Y-%m-%d %H:%M:%S.") + f"{t.microsecond // 1000:03d}" if isinstance(t, datetime) else _s(t)
    return hashlib.sha256("|".join([ts] + [_s(row.get(c)) for c in cols]).encode()).hexdigest()


# ---------------------------------------------------------------- normalization (NORMALIZE_TAIL)
UPN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SID = re.compile(r"^S-1-\d+(-\d+)+$")
GUID = re.compile(r"^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")
IPV4_IN = re.compile(r"(\d{1,3}(?:\.\d{1,3}){3})")


def normalize(entity: str, value: str, nulls: list[str]) -> tuple[str, str, str] | None:
    """Returns (Value, ValueType, ValueNorm) or None when the value is dropped."""
    v = (value or "").replace('"', "").replace("'", "").strip()
    if v.lower() in [str(n) for n in nulls] or not v:
        return None
    if entity in ("url", "domain"):
        v = v.replace("hxxp", "http").replace("[.]", ".").replace("[:]", ":")
    if entity == "ip":
        vt = "IPv6" if v.count(":") >= 2 else "IPv4"
    elif entity == "user":
        vt = ("SID" if SID.match(v) else "AADID" if GUID.match(v) else "Windows" if "\\" in v
              else "DN" if v.startswith("CN=") else "UPN" if UPN.match(v) else "Simple")
    elif entity == "host":
        vt = "FQDN" if "." in v else "Hostname"
    elif entity == "hash":
        vt = {32: "MD5", 40: "SHA1", 64: "SHA256"}.get(len(v), "Other")
    else:
        vt = {"url": "URL", "email": "UPN", "domain": "FQDN"}.get(entity, "Other")

    if vt == "IPv4":
        m = IPV4_IN.search(v)
        n = m.group(1) if m else ""
    elif vt == "IPv6":
        n = re.sub(r"[\[\]]", "", v.split("%")[0]).lower()
    elif vt in ("SID", "AADID"):
        n = v.upper()
    elif vt == "Windows":
        n = v.split("\\")[1].lower()
    elif vt == "DN":
        m = re.match(r"^CN=([^,]+)", v)
        n = m.group(1).lower() if m else ""
    elif entity == "user" and vt == "UPN":
        n = v.split("@")[0].lower()
    elif entity == "host" and "\\" in v:
        n = v.split("\\")[1].lower()
    elif entity == "host" and vt == "FQDN":
        n = v.split(".")[0].lower()
    elif entity == "domain":
        n = v.rstrip(".").lower()
    else:
        n = v.lower()

    if vt == "IPv4":
        try:
            ipaddress.IPv4Address(n)
        except ValueError:
            return None
    if entity == "host" and re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", v):
        return None
    if entity == "hash" and vt == "Other":
        return None
    if not n:
        return None
    return v, vt, n


# ---------------------------------------------------------------- entity and event rows
def _ent(entity: str, role: str, value: str, layer: str, tier: int) -> dict:
    return {"EntityType": entity, "Role": role, "Value": value, "MappingLayer": layer, "MappingTier": int(tier)}


def _meta(row: Row, group: dict, event_type: str, event_result: str) -> dict:
    return {"EventStartTime": row["_EventStartTime"], "SourceRecordKey": row["_SourceRecordKey"],
            "SourceTable": group["table"], "SourceGroup": group["id"],
            "EventVendor": group.get("vendor", ""), "EventProduct": group.get("product", ""),
            "EventSchema": group.get("schema", ""), "EventType": event_type, "EventResult": event_result}


def template_hits(text: str, templates: list[dict]) -> list[tuple[dict, re.Match]]:
    out = []
    for t in templates:
        m = re.search(t["regex"], text or "")
        if m and t["match"] in (text or ""):
            out.append((t, m))
    return out


def occurrence_rows(rows: Iterable[Row], group: dict, vocab: dict) -> list[dict]:
    """One row per entity occurrence (the shape inside every job, before the hourly rollup)."""
    tier = int(group.get("tier", 2))
    fields = [f for f in group.get("fields", []) if f.get("entity")]
    consts = [c for c in group.get("constant_entities", []) if c.get("entity")]
    text = group.get("text_column")
    templates = group.get("templates", []) or []
    nulls = vocab.get("null_values", [])
    out = []
    for row in rows:
        produced: list[tuple[dict, dict]] = []
        if fields or (consts and not text):
            meta = _meta(row, group, event_type_value(row, group), result_value(row, group, vocab))
            for f in fields + consts:
                produced.append((meta, _ent(f["entity"], f.get("role", "Unknown"), field_value(row, f), "registry", tier)))
        if text:
            body = _s(row.get(text))
            hits = template_hits(body, templates)
            any_regex = any(re.search(t["regex"], body) for t in templates)
            for t, m in hits:
                t_tier = int(t.get("tier", tier))
                meta = _meta(row, group, t.get("event_type", ""), t.get("event_result", ""))
                for name, s in (t.get("slots") or {}).items():
                    if s and s.get("entity"):
                        produced.append((meta, _ent(s["entity"], s.get("role", "Unknown"), m.group(name) or "", "template", t_tier)))
                if not fields:
                    for c in consts:
                        produced.append((meta, _ent(c["entity"], c["role"], field_value(row, c), "template", t_tier)))
            if not any_regex:
                meta = _meta(row, group, "", "")
                for etype, pattern in CLASSIFIER:
                    for v in re.findall(pattern, body):
                        produced.append((meta, _ent(etype, "Unknown", v, "classifier", 2)))
                if consts and not fields:
                    for c in consts:
                        produced.append((meta, _ent(c["entity"], c["role"], field_value(row, c), "registry", 2)))
        for meta, e in produced:
            n = normalize(e["EntityType"], e["Value"], nulls)
            if n is None:
                continue
            r = {**meta, **e, "Value": n[0], "ValueType": n[1], "ValueNorm": n[2]}
            out.append({c: r.get(c) for c, _ in OCC_COLUMNS})
    return out


def _hour(t: datetime) -> datetime:
    return t.replace(minute=0, second=0, microsecond=0)


def rollup_rows(occ: list[dict]) -> list[dict]:
    """HuntEntity rows: one per hour, group, entity, role and result, as notebook 02 builds them.
    Value is the smallest original form and SampleKeys the first record keys in sort order."""
    agg: dict[tuple, dict] = {}
    for o in occ:
        k = (_hour(o["EventStartTime"]),) + tuple(o[c] for c in ROLLUP_KEYS)
        a = agg.get(k)
        if a is None:
            a = agg[k] = {"Hour": k[0], **{c: o[c] for c in ROLLUP_KEYS}, "Count": 0, "Value": o["Value"],
                          "FirstSeen": o["EventStartTime"], "LastSeen": o["EventStartTime"], "_keys": set()}
        a["Count"] += 1
        a["Value"] = min(a["Value"], o["Value"])
        a["FirstSeen"] = min(a["FirstSeen"], o["EventStartTime"])
        a["LastSeen"] = max(a["LastSeen"], o["EventStartTime"])
        a["_keys"].add(o["SourceRecordKey"])
    out = []
    for a in agg.values():
        a["SampleKeys"] = sorted(a.pop("_keys"))[:SAMPLE_KEYS]
        out.append({c: a.get(c) for c, _ in ENTITY_COLUMNS})
    return out


def stats_rows(base: list[Row], occ: list[dict], group: dict) -> list[dict]:
    """_stats rows per hour: RowsRead, RowsWithEntity and (text groups with templates) RowsTemplateMatched."""
    def bucket(items, key_of):
        b: dict[datetime, dict] = {}
        for t, key in items:
            x = b.setdefault(_hour(t), {"keys": set(), "n": 0, "lo": t, "hi": t})
            x["n"] += 1
            x["keys"].add(key_of(key))
            x["lo"], x["hi"] = min(x["lo"], t), max(x["hi"], t)
        return b
    parts = [("RowsRead", bucket([(r["_EventStartTime"], r["_SourceRecordKey"]) for r in base], id), "n"),
             ("RowsWithEntity", bucket([(o["EventStartTime"], o["SourceRecordKey"]) for o in occ], str), "keys")]
    if group.get("text_column") and group.get("templates"):
        parts.append(("RowsTemplateMatched", bucket([(o["EventStartTime"], o["SourceRecordKey"]) for o in occ
                                                     if o["MappingLayer"] == "template"], str), "keys"))
    out = []
    for role, b, how in parts:
        for h, x in b.items():
            out.append({c: "" for c, t in ENTITY_COLUMNS if t == "string"} | {
                "Hour": h, "FirstSeen": x["lo"], "LastSeen": x["hi"], "SourceTable": group["table"],
                "SourceGroup": group["id"], "EntityType": "_stats", "Role": role, "MappingTier": None,
                "Count": x["n"] if how == "n" else len(x["keys"]), "SampleKeys": []})
    return out


def _clean(name: str, value: str, nulls: list[str]) -> str:
    c = (value or "").strip()
    if c.lower() in [str(n) for n in nulls]:
        c = ""
    if name.endswith("IpAddr"):
        if c.count(":") >= 2:
            c = re.sub(r"[\[\]]", "", c.split("%")[0]).lower()
        else:
            m = IPV4_IN.search(c)
            c = m.group(1) if m else ""
    return c


_EVENT_NAMES = {c for c, _ in EVENT_COLUMNS}


def _event_record(mapped: dict) -> dict:
    rec = {}
    for name, typ in EVENT_COLUMNS:
        v = mapped.get(name)
        if typ == "int":
            rec[name] = int(v) if isinstance(v, (int, str)) and str(v).lstrip("-").isdigit() else None
        elif typ == "datetime":
            rec[name] = v
        else:
            rec[name] = "" if v is None else str(v)
    return rec


def event_rows(rows: Iterable[Row], group: dict, vocab: dict) -> list[dict]:
    """HuntEvent rows: Tier 1 groups with field rules, and Tier 1 templates on text sources."""
    nulls = vocab.get("null_values", [])
    by_fields = int(group.get("tier", 2)) == 1 and bool(group.get("fields"))
    templates = event_templates(group)
    if not by_fields and not templates:
        return []
    consts = [c for c in group.get("constant_entities", []) if c.get("asim")]
    text = group.get("text_column")
    out = []
    for row in rows:
        if by_fields:
            mapped: dict[str, Any] = {}
            for f in group["fields"] + consts:
                if f.get("asim"):
                    mapped[f["asim"]] = _clean(f["asim"], field_value(row, f), nulls)
            mapped.update(_meta(row, group, event_type_value(row, group), result_value(row, group, vocab)))
            mapped["MappingTier"] = 1
            out.append(_event_record(mapped))
        if templates:
            body = _s(row.get(text))
            for t, m in template_hits(body, templates):
                mapped = {c["asim"]: _clean(c["asim"], field_value(row, c), nulls) for c in consts}
                for name, slot in (t.get("slots") or {}).items():
                    col = slot_asim(slot or {})
                    if col and col in _EVENT_NAMES:
                        mapped[col] = _clean(col, m.group(name) or "", nulls)
                mapped.update(_meta(row, group, t.get("event_type", ""), t.get("event_result", "")))
                mapped["MappingTier"] = 1
                out.append(_event_record(mapped))
    return out


# ---------------------------------------------------------------- filters (registry filter subset)
def make_filter(group: dict):
    """The registry's `py_filter` (a dict of column -> value or list) selects rows in Python.
    The KQL `filter` and Spark `spark_filter` remain the source of truth in the lake."""
    spec = group.get("py_filter") or {}

    text, excl = group.get("text_column"), [x for x in group.get("exclude_text") or [] if x]

    def ok(row: Row) -> bool:
        if excl and text and any(x in _s(row.get(text)) for x in excl):
            return False
        for col, want in spec.items():
            have = row.get(col)
            if isinstance(want, list):
                if have not in want and _s(have) not in [str(w) for w in want]:
                    return False
            elif isinstance(want, str) and want.endswith("*"):
                if not _s(have).startswith(want[:-1]):
                    return False
            elif have != want and _s(have) != str(want):
                return False
        return True
    return ok


def prepare(rows: Iterable[Row], group: dict) -> list[Row]:
    tc = group.get("time_column", "TimeGenerated")
    keep = make_filter(group)
    out = []
    for r in rows:
        if not keep(r):
            continue
        r = dict(r)
        r["_EventStartTime"] = r.get(tc)
        r["_SourceRecordKey"] = record_key(r, group)
        out.append(r)
    return out


def index_parts(rows: Iterable[Row], group: dict, vocab: dict) -> dict[str, list]:
    """Everything one indexing pass produces: the prepared raw rows, the occurrence rows
    (intermediate), the HuntEntity rows (hourly rollup plus _stats) and the HuntEvent rows."""
    base = prepare(rows, group)
    occ = occurrence_rows(base, group, vocab)
    return {"base": base, "occ": occ, "entity": rollup_rows(occ) + stats_rows(base, occ, group),
            "event": event_rows(base, group, vocab)}


def index_group(rows: Iterable[Row], group: dict, vocab: dict) -> tuple[list[dict], list[dict]]:
    """HuntEntity rows (rollup and _stats) and HuntEvent rows for one group."""
    p = index_parts(rows, group, vocab)
    return p["entity"], p["event"]
