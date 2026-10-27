"""Coverage metrics per grammar group (same definitions as kit/notebooks/03_coverage.py).

Everything comes from the group's HuntEntity rows: the _stats rows written by each indexing run
(RowsRead, RowsWithEntity, RowsTemplateMatched) and the hourly rollup rows. No source table is read.
"""
from __future__ import annotations

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


def _sums(ents: list[dict]) -> dict[str, int]:
    s: dict[str, int] = defaultdict(int)
    for e in ents:
        if e["EntityType"] == "_stats":
            s[e["Role"]] += int(e["Count"])
    return s


def group_coverage(group: dict, ents: list[dict], min_extraction: float = 0.9, min_template: float = 0.7) -> dict:
    """`ents` are the group's HuntEntity rows (rollup plus _stats)."""
    s = _sums(ents)
    rows = [e for e in ents if e["EntityType"] != "_stats"]
    n, indexed, templ = s.get("RowsRead", 0), s.get("RowsWithEntity", 0), s.get("RowsTemplateMatched", 0)
    occ = sum(int(e["Count"]) for e in rows)
    unknown = sum(int(e["Count"]) for e in rows if e["Role"] == "Unknown")
    has_tpl = bool(group.get("text_column") and group.get("templates"))
    tier = 1 if (group.get("fields") or group.get("templates")) and int(group.get("tier", 1)) == 1 else 2
    last = max((e["LastSeen"] for e in rows), default=None)
    c = {"SourceGroup": group["id"], "SourceTable": group["table"], "Tier": tier, "Layer": group.get("layer", ""),
         "Engine": group.get("engine", "notebook"), "RawRows": n, "IndexedRows": indexed,
         "EntityRows": occ, "RollupRows": len(rows), "ExtractionRate": round(indexed / n, 4) if n else 0.0,
         "TemplateMatchRate": round(templ / n, 4) if (has_tpl and n) else (0.0 if has_tpl else None),
         "UnknownRoleShare": round(unknown / occ, 4) if occ else 0.0,
         "LastIndexed": last.strftime("%Y-%m-%dT%H:%M:%SZ") if isinstance(last, datetime) else None}
    c["Status"] = status_of(c, min_extraction, min_template)
    return c


def daily_history(group: dict, ents: list[dict], days: int = 7) -> list[dict]:
    """Raw and indexed rows per day from the hourly _stats rows."""
    today = datetime.now(timezone.utc).date()
    by: dict = defaultdict(lambda: defaultdict(int))
    for e in ents:
        if e["EntityType"] == "_stats" and isinstance(e["Hour"], datetime):
            by[e["Hour"].date()][e["Role"]] += int(e["Count"])
    out = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        n, k = by[d]["RowsRead"], by[d]["RowsWithEntity"]
        out.append({"day": d.isoformat(), "raw": n, "indexed": k, "extraction": round(k / n, 4) if n else None})
    return out
