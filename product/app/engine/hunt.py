"""Hunt tools over an in-memory index (demo mode and tests). Same semantics as the KQL in
app/kit/tools.yaml, which the live provider runs against the lake."""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

ENTITY_TYPES = ("ip", "host", "user", "hash", "url", "domain", "email")
ROLES = ("Src", "Dst", "Actor", "Target", "Dvc", "Unknown", "*")


def value_forms(value: str) -> tuple[str, str]:
    v = value.strip().lower()
    if "\\" in v:
        short = v.split("\\")[1]
    elif re.match(r"^[^@\s]+@[^@\s]+$", v):
        short = v.split("@")[0]
    elif re.match(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$", v) and not re.match(r"^\d{1,3}(\.\d{1,3}){3}$", v):
        short = v.split(".")[0]
    else:
        short = v
    return v, short


def _since(days: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def _iso(t: Any) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z" if isinstance(t, datetime) else str(t)


def hunt_value(ents: list[dict], value: str, days: float = 7) -> list[dict]:
    v, short = value_forms(value)
    since = _since(days)
    agg: dict[tuple, dict] = {}
    for e in ents:
        if e["EventStartTime"] < since:
            continue
        if e["ValueNorm"] not in (v, short) and (e["Value"] or "").lower() != v:
            continue
        k = (e["SourceTable"], e["SourceGroup"], e["EntityType"])
        a = agg.setdefault(k, {"SourceTable": k[0], "SourceGroup": k[1], "EntityType": k[2], "Events": 0,
                               "FirstSeen": e["EventStartTime"], "LastSeen": e["EventStartTime"], "Roles": set(),
                               "ValueForms": set(), "Tiers": set(), "EventTypes": set(), "Results": set()})
        a["Events"] += 1
        a["FirstSeen"] = min(a["FirstSeen"], e["EventStartTime"])
        a["LastSeen"] = max(a["LastSeen"], e["EventStartTime"])
        a["Roles"].add(e["Role"]); a["ValueForms"].add(e["Value"]); a["Tiers"].add(e["MappingTier"])
        if e["EventType"]:
            a["EventTypes"].add(e["EventType"])
        if e["EventResult"]:
            a["Results"].add(e["EventResult"])
    out = []
    for a in sorted(agg.values(), key=lambda x: -x["Events"]):
        out.append({**a, "FirstSeen": _iso(a["FirstSeen"]), "LastSeen": _iso(a["LastSeen"]),
                    **{k: sorted(a[k]) for k in ("Roles", "ValueForms", "Tiers", "EventTypes", "Results")}})
    return out


def hunt_entity(ents: list[dict], etype: str, value: str, role: str = "*", days: float = 7) -> list[dict]:
    v = value.strip().lower()
    since = _since(days)
    agg: dict[tuple, dict] = {}
    for e in ents:
        if e["EventStartTime"] < since or e["EntityType"] != etype or (role != "*" and e["Role"] != role):
            continue
        if not (e["ValueNorm"] == v or (e["Value"] or "").lower() == v or (etype == "url" and v in e["ValueNorm"])):
            continue
        k = (e["SourceTable"], e["SourceGroup"], e["Role"])
        a = agg.setdefault(k, {"SourceTable": k[0], "SourceGroup": k[1], "Role": k[2], "Events": 0,
                               "FirstSeen": e["EventStartTime"], "LastSeen": e["EventStartTime"],
                               "Results": set(), "Tiers": set()})
        a["Events"] += 1
        a["FirstSeen"] = min(a["FirstSeen"], e["EventStartTime"]); a["LastSeen"] = max(a["LastSeen"], e["EventStartTime"])
        if e["EventResult"]:
            a["Results"].add(e["EventResult"])
        a["Tiers"].add(e["MappingTier"])
    return [{**a, "FirstSeen": _iso(a["FirstSeen"]), "LastSeen": _iso(a["LastSeen"]),
             "Results": sorted(a["Results"]), "Tiers": sorted(a["Tiers"])}
            for a in sorted(agg.values(), key=lambda x: -x["Events"])]


def auth_events(ents: list[dict], user: str, result: str = "*", days: float = 7) -> list[dict]:
    v, _ = value_forms(user)
    short = v.split("\\")[1] if "\\" in v else v.split("@")[0] if "@" in v else v
    since = _since(days)
    src_by_key: dict[str, str] = {}
    for e in ents:
        if e["EntityType"] == "ip" and e["Role"] == "Src":
            src_by_key.setdefault(e["SourceRecordKey"], e["ValueNorm"])
    out = []
    for e in ents:
        if e["EventStartTime"] < since or e["EntityType"] != "user" or e["ValueNorm"] != short or e["MappingTier"] != 1:
            continue
        if not (e["EventType"] in ("Logon", "Logoff") or e["EventSchema"] == "Authentication"):
            continue
        if result != "*" and e["EventResult"] != result:
            continue
        out.append({"EventStartTime": _iso(e["EventStartTime"]), "SourceTable": e["SourceTable"],
                    "SourceGroup": e["SourceGroup"], "EventType": e["EventType"], "EventResult": e["EventResult"],
                    "User": e["Value"], "SrcIpAddr": src_by_key.get(e["SourceRecordKey"], ""),
                    "SourceRecordKey": e["SourceRecordKey"], "_t": e["EventStartTime"]})
    out.sort(key=lambda r: r["_t"], reverse=True)
    for r in out:
        r.pop("_t")
    return out[:500]


def network_events(evs: list[dict], ip: str, days: float = 7) -> list[dict]:
    ip = ip.strip().lower()
    since = _since(days)
    agg: dict[tuple, dict] = {}
    for e in evs:
        if e["EventStartTime"] < since or ip not in (e.get("SrcIpAddr"), e.get("DstIpAddr")):
            continue
        if e.get("EventSchema") != "NetworkSession" and not e.get("DstIpAddr"):
            continue
        k = (e["SourceGroup"], e["SrcIpAddr"], e["DstIpAddr"], e.get("DstPortNumber"))
        a = agg.setdefault(k, {"SourceGroup": k[0], "SrcIpAddr": k[1], "DstIpAddr": k[2], "DstPortNumber": k[3],
                               "Sessions": 0, "FirstSeen": e["EventStartTime"], "LastSeen": e["EventStartTime"],
                               "Actions": set(), "Results": set()})
        a["Sessions"] += 1
        a["FirstSeen"] = min(a["FirstSeen"], e["EventStartTime"]); a["LastSeen"] = max(a["LastSeen"], e["EventStartTime"])
        if e.get("DvcAction"):
            a["Actions"].add(e["DvcAction"])
        if e.get("EventResult"):
            a["Results"].add(e["EventResult"])
    return [{**a, "FirstSeen": _iso(a["FirstSeen"]), "LastSeen": _iso(a["LastSeen"]),
             "Actions": sorted(a["Actions"]), "Results": sorted(a["Results"])}
            for a in sorted(agg.values(), key=lambda x: -x["Sessions"])][:500]


def timeline(ents: list[dict], value: str, days: float = 7) -> list[dict]:
    """Every index event touching the value, oldest first, one row per event."""
    v, short = value_forms(value)
    since = _since(days)
    keys = {}
    for e in ents:
        if e["EventStartTime"] >= since and (e["ValueNorm"] in (v, short) or (e["Value"] or "").lower() == v):
            keys[(e["SourceGroup"], e["SourceRecordKey"])] = e
    others = defaultdict(list)
    for e in ents:
        k = (e["SourceGroup"], e["SourceRecordKey"])
        if k in keys:
            others[k].append(f"{e['EntityType']}:{e['Role']}={e['Value']}")
    out = []
    for k, e in sorted(keys.items(), key=lambda kv: kv[1]["EventStartTime"]):
        out.append({"EventStartTime": _iso(e["EventStartTime"]), "SourceTable": e["SourceTable"],
                    "SourceGroup": e["SourceGroup"], "EventType": e["EventType"], "EventResult": e["EventResult"],
                    "MatchedAs": f"{e['EntityType']}:{e['Role']}", "Tier": e["MappingTier"],
                    "Entities": sorted(set(others[k])), "SourceRecordKey": e["SourceRecordKey"]})
    return out


def related(ents: list[dict], value: str, days: float = 7, limit: int = 25) -> list[dict]:
    """Other entities seen in the same events as the value: the next things to pivot on."""
    v, short = value_forms(value)
    since = _since(days)
    keys = {(e["SourceGroup"], e["SourceRecordKey"]) for e in ents
            if e["EventStartTime"] >= since and (e["ValueNorm"] in (v, short) or (e["Value"] or "").lower() == v)}
    agg: dict[tuple, dict] = {}
    for e in ents:
        if (e["SourceGroup"], e["SourceRecordKey"]) not in keys or e["ValueNorm"] in (v, short):
            continue
        k = (e["EntityType"], e["ValueNorm"])
        a = agg.setdefault(k, {"EntityType": k[0], "Value": e["ValueNorm"], "Events": 0, "Sources": set(), "Roles": set()})
        a["Events"] += 1; a["Sources"].add(e["SourceGroup"]); a["Roles"].add(e["Role"])
    return [{**a, "Sources": sorted(a["Sources"]), "Roles": sorted(a["Roles"])}
            for a in sorted(agg.values(), key=lambda x: (-len(x["Sources"]), -x["Events"]))][:limit]
