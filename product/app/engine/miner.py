"""Pure-Python field inventory and template mining (same rules as kit/notebooks/01).

Turns sample rows from an unknown table into field proposals (proposed ASIM name, entity,
role, value class, fill rate, sample values) and message templates for text columns.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from typing import Any

TEXT_COLUMNS = ["SyslogMessage", "RawData", "Message", "Msg", "EventMessage"]
VALUE_CLASSES = {
    "ip": r"^\[?(\d{1,3}(\.\d{1,3}){3}|[0-9a-fA-F:]*:[0-9a-fA-F:]+)\]?(:\d+)?$",
    "upn": r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$",
    "windows_user": r"^[A-Za-z0-9._-]+\\[A-Za-z0-9._$-]+$",
    "sid": r"^S-1-\d+(-\d+)+$",
    "hash": r"^([a-fA-F0-9]{32}|[a-fA-F0-9]{40}|[a-fA-F0-9]{64})$",
    "url": r"^(https?|hxxps?)://",
    "fqdn": r"^([A-Za-z0-9-]+\.)+[A-Za-z]{2,}$",
    "guid": r"^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$",
}
CLASS_TO_ENTITY = {"ip": "ip", "upn": "user", "windows_user": "user", "sid": "user",
                   "hash": "hash", "url": "url", "fqdn": "host"}
MASKS = [
    (r"\b\d{1,3}(?:\.\d{1,3}){3}\b", "<IP>"),
    (r"\b[0-9a-fA-F]{8}-[0-9a-fA-F-]{27}\b", "<UUID>"),
    (r"\b[0-9a-fA-F]{16,}\b", "<HEX>"),
    (r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b", "<EMAIL>"),
    (r"(?:/[\w.-]+)+", "<PATH>"),
    (r"\b\d+\b", "<NUM>"),
]
KV = re.compile(r"(?:^|[\s;|,])([A-Za-z][\w.-]{0,40})=(\"[^\"]*\"|[^\s;|,]*)")
SLOT_FOR_TOKEN = {"<IP>": r"(\S+)", "<EMAIL>": r"(\S+)", "<UUID>": r"(\S+)", "<HEX>": r"(\S+)",
                  "<PATH>": r"(\S+)", "<NUM>": r"(\d+)"}
SKIP = {"TimeGenerated", "TenantId", "Type", "_ResourceId", "SourceSystem", "MG", "ManagementGroupName"}


def squash(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def propose(name: str, vocab: dict) -> tuple[str, str]:
    s = squash(name.split(".")[-1])
    asim = next((a for a, syn in vocab.get("synonyms", {}).items() if s in [squash(x) for x in syn]), "")
    role = "Unknown"
    for r in ("Src", "Dst", "Actor", "Target", "Dvc"):
        if any(tok in s for tok in vocab.get("role_tokens", {}).get(r, [])):
            role = r
            break
    return asim, role


def classify_values(values: list[str]) -> dict[str, float]:
    n = max(len(values), 1)
    return {c: sum(1 for v in values if v and re.search(p, v)) / n for c, p in VALUE_CLASSES.items()}


def flatten_json(obj: Any, prefix: str = ""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from flatten_json(v, f"{prefix}.{k}" if prefix else k)
    elif isinstance(obj, list):
        for v in obj[:5]:
            yield from flatten_json(v, prefix + "[]")
    else:
        yield prefix, None if obj is None else str(obj)


def _row(table, path, kind, dtype, vals, n, vocab):
    present = [v for v in vals if v not in (None, "")]
    cls = classify_values(present)
    top = max(cls, key=cls.get) if cls else ""
    share = cls.get(top, 0)
    asim, role = propose(path, vocab)
    entity = CLASS_TO_ENTITY.get(top, "") if share >= 0.5 else ""
    samples = [v[:120] for v, _ in Counter(present).most_common(5)]
    return {"table": table, "field": path, "kind": kind, "dataType": dtype,
            "fillRate": round(len(present) / max(n, 1), 4), "valueClass": top if share >= 0.5 else "",
            "valueClassShare": round(share, 4), "proposedAsim": asim, "proposedRole": role,
            "proposedEntity": entity, "samples": samples,
            "confidence": _confidence(asim, entity, share, role)}


def _confidence(asim: str, entity: str, share: float, role: str) -> str:
    if asim and entity and share >= 0.9:
        return "high"
    if entity and (asim or role != "Unknown"):
        return "medium"
    return "low" if entity else "none"


def inventory(table: str, rows: list[dict], vocab: dict) -> list[dict]:
    if not rows:
        return []
    n = len(rows)
    cols = [c for c in rows[0].keys() if c not in SKIP and not c.startswith("_")]
    out = []
    for col in cols:
        vals = [None if r.get(col) is None else (r[col] if isinstance(r[col], (dict, list)) else str(r[col])) for r in rows]
        sv = [v if isinstance(v, str) or v is None else json.dumps(v) for v in vals]
        dtype = type(rows[0].get(col)).__name__ if rows[0].get(col) is not None else "string"
        out.append(_row(table, col, "column", dtype, sv, n, vocab))
        texts = [v for v in vals if v]
        if not texts:
            continue
        is_json = sum(isinstance(t, (dict, list)) or str(t).lstrip().startswith("{") for t in texts) / len(texts) > 0.5
        if is_json:
            keyvals: dict[str, list] = defaultdict(list)
            for t in texts:
                try:
                    obj = t if isinstance(t, (dict, list)) else json.loads(t)
                except ValueError:
                    continue
                for path, v in flatten_json(obj):
                    keyvals[path].append(v)
            out += [_row(table, f"{col}.{p}", "json", "string", v, len(texts), vocab) for p, v in keyvals.items()]
        elif sum(1 for t in texts if len(KV.findall(str(t))) >= 2) / len(texts) > 0.5:
            keyvals = defaultdict(list)
            for t in texts:
                for k, v in KV.findall(str(t)):
                    keyvals[k].append(v.strip('"'))
            out += [_row(table, f"{col}.{p}", "kv", "string", v, len(texts), vocab) for p, v in keyvals.items()]
    return out


def mask(text: str) -> str:
    for pattern, token in MASKS:
        text = re.sub(pattern, token, text)
    return text


def template_regex(template: str, example: str) -> tuple[str, list[str]]:
    """A starting regex for a mined template: literal text kept, each token a numbered slot.
    Returns the regex with named groups slot1..slotN and the token list (analyst renames slots)."""
    parts = re.split(r"(<IP>|<UUID>|<HEX>|<EMAIL>|<PATH>|<NUM>)", template)
    rx, tokens = "", []
    for p in parts:
        if p in SLOT_FOR_TOKEN:
            tokens.append(p)
            rx += f"(?P<slot{len(tokens)}>{SLOT_FOR_TOKEN[p][1:-1]})"
        else:
            rx += re.escape(p)
    if not re.search(rx, example):
        rx = re.sub(r"\\\s|\\ ", r"\\s+", rx)
    return rx, tokens


def mine_templates(table: str, rows: list[dict], top_n: int = 20) -> list[dict]:
    if not rows:
        return []
    text = next((c for c in TEXT_COLUMNS if c in rows[0]), None)
    if not text:
        return []
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for r in rows:
        body = str(r.get(text) or "")
        key = str(r.get("ProcessName") or (body.split()[0] if body.split() else ""))
        groups[(key, mask(body))].append(body)
    total = len(rows)
    out = []
    for (key, tpl), lines in sorted(groups.items(), key=lambda kv: -len(kv[1]))[:top_n]:
        rx, tokens = template_regex(tpl, lines[0])
        anchor = re.split(r"<[A-Z]+>", tpl)[0].strip() or tpl[:20]
        anchor = max(re.split(r"<[A-Z]+>", tpl), key=len).strip()[:40]
        out.append({"table": table, "textColumn": text, "groupKey": key, "template": tpl, "lines": len(lines),
                    "share": round(len(lines) / total, 4), "example": lines[0], "suggestedRegex": rx,
                    "suggestedMatch": anchor, "tokens": tokens})
    return out
