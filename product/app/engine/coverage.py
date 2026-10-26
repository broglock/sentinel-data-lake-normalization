"""Coverage metrics per grammar group (same definitions as kit/notebooks/03_coverage.py)."""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone


def status_of(c: dict, min_extraction: float, min_template: float) -> str:
    if c["RawRows"] == 0:
        return "no-data"
    if c["Tier"] == 2:
        return "classifier-only"
    if c["ExtractionRate"] < min_extraction:
        return "review"
    if c["TemplateMatchRate"] is not None and c["TemplateMatchRate"] < min_template:
        return "review"
    return "ok"


def group_coverage(group: dict, raw: list[dict], ents: list[dict], min_extraction: float = 0.9,
                   min_template: float = 0.7) -> dict:
    keys_with = {e["SourceRecordKey"] for e in ents}
    n = len(raw)
    text = group.get("text_column")
    tmatch = None
    if text and group.get("templates"):
        hit = sum(1 for r in raw if any(re.search(t["regex"], str(r.get(text) or "")) for t in group["templates"]))
        tmatch = hit / n if n else 0.0
    unknown = sum(1 for e in ents if e["Role"] == "Unknown") / len(ents) if ents else 0.0
    tier = 1 if (group.get("fields") or group.get("templates")) and int(group.get("tier", 1)) == 1 else 2
    last = max((e["EventStartTime"] for e in ents), default=None)
    c = {"SourceGroup": group["id"], "SourceTable": group["table"], "Tier": tier, "Layer": group.get("layer", ""),
         "Engine": group.get("engine", "notebook"), "RawRows": n, "IndexedRows": len(keys_with),
         "EntityRows": len(ents), "ExtractionRate": round(len(keys_with) / n, 4) if n else 0.0,
         "TemplateMatchRate": round(tmatch, 4) if tmatch is not None else None,
         "UnknownRoleShare": round(unknown, 4),
         "LastIndexed": last.strftime("%Y-%m-%dT%H:%M:%SZ") if isinstance(last, datetime) else None}
    c["Status"] = status_of(c, min_extraction, min_template)
    return c


def daily_history(group: dict, raw: list[dict], ents: list[dict], days: int = 7) -> list[dict]:
    tc = group.get("time_column", "TimeGenerated")
    today = datetime.now(timezone.utc).date()
    raw_by = defaultdict(int)
    for r in raw:
        t = r.get(tc)
        if isinstance(t, datetime):
            raw_by[t.date()] += 1
    keys_by = defaultdict(set)
    for e in ents:
        keys_by[e["EventStartTime"].date()].add(e["SourceRecordKey"])
    out = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        n = raw_by.get(d, 0)
        out.append({"day": d.isoformat(), "raw": n, "indexed": len(keys_by.get(d, ())),
                    "extraction": round(len(keys_by.get(d, ())) / n, 4) if n else None})
    return out
