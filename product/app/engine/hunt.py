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


def _match(e: dict, v: str, short: str) -> bool:
    return e["ValueNorm"] in (v, short) or (e["Value"] or "").lower() == v


def _rows(ents: list[dict], since: datetime) -> list[dict]:
    """HuntEntity rollup rows in the window (the _stats rows are job counts, not entities)."""
    return [e for e in ents if e["EntityType"] != "_stats" and e["Hour"] > since]


def hunt_value(ents: list[dict], value: str, days: float = 7) -> list[dict]:
    v, short = value_forms(value)
    agg: dict[tuple, dict] = {}
    for e in _rows(ents, _since(days)):
        if not _match(e, v, short):
            continue
        k = (e["SourceTable"], e["SourceGroup"], e["EntityType"])
        a = agg.setdefault(k, {"SourceTable": k[0], "SourceGroup": k[1], "EntityType": k[2], "Events": 0,
                               "FirstSeen": e["FirstSeen"], "LastSeen": e["LastSeen"], "Roles": set(),
                               "ValueForms": set(), "Tiers": set(), "EventTypes": set(), "Results": set()})
        a["Events"] += int(e["Count"])
        a["FirstSeen"] = min(a["FirstSeen"], e["FirstSeen"])
        a["LastSeen"] = max(a["LastSeen"], e["LastSeen"])
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
    agg: dict[tuple, dict] = {}
    for e in _rows(ents, _since(days)):
        if e["EntityType"] != etype or (role != "*" and e["Role"] != role):
            continue
        if not (e["ValueNorm"] == v or (e["Value"] or "").lower() == v or (etype == "url" and v in e["ValueNorm"])):
            continue
        k = (e["SourceTable"], e["SourceGroup"], e["Role"])
        a = agg.setdefault(k, {"SourceTable": k[0], "SourceGroup": k[1], "Role": k[2], "Events": 0,
                               "FirstSeen": e["FirstSeen"], "LastSeen": e["LastSeen"],
                               "Results": set(), "Tiers": set()})
        a["Events"] += int(e["Count"])
        a["FirstSeen"] = min(a["FirstSeen"], e["FirstSeen"]); a["LastSeen"] = max(a["LastSeen"], e["LastSeen"])
        if e["EventResult"]:
            a["Results"].add(e["EventResult"])
        a["Tiers"].add(e["MappingTier"])
    return [{**a, "FirstSeen": _iso(a["FirstSeen"]), "LastSeen": _iso(a["LastSeen"]),
             "Results": sorted(a["Results"]), "Tiers": sorted(a["Tiers"])}
            for a in sorted(agg.values(), key=lambda x: -x["Events"])]


def _user_short(u: str) -> str:
    u = (u or "").lower()
    return u.split("\\")[1] if "\\" in u else u.split("@")[0] if "@" in u else u


def auth_events(evs: list[dict], user: str, result: str = "*", days: float = 7) -> list[dict]:
    """Sign-ins from HuntEvent (Tier 1 sources, hourly rollup), matched on the short form of the user.
    One row per hour, source, user, source IP and result, with Count."""
    short = _user_short(user.strip())
    since = _since(days)
    out = []
    for e in evs:
        if e["Hour"] <= since:
            continue
        if not (e["EventType"] in ("Logon", "Logoff") or e["EventSchema"] == "Authentication"):
            continue
        u = e.get("TargetUsername") or e.get("ActorUsername") or ""
        if _user_short(u) != short or (result != "*" and e["EventResult"] != result):
            continue
        keys = list(e["SampleKeys"] or [])
        out.append({"EventStartTime": _iso(e["FirstSeen"]), "LastSeen": _iso(e["LastSeen"]), "Count": int(e["Count"]),
                    "SourceTable": e["SourceTable"], "SourceGroup": e["SourceGroup"], "EventType": e["EventType"],
                    "EventResult": e["EventResult"], "User": u, "SrcIpAddr": e.get("SrcIpAddr") or "",
                    "SampleKeys": keys, "SourceRecordKey": (keys or [""])[0], "_t": e["FirstSeen"]})
    out.sort(key=lambda r: (r["_t"], r["SourceGroup"], r["User"], r["SrcIpAddr"]), reverse=True)
    for r in out:
        r.pop("_t")
    return out[:500]


def network_events(evs: list[dict], ip: str, days: float = 7) -> list[dict]:
    ip = ip.strip().lower()
    since = _since(days)
    agg: dict[tuple, dict] = {}
    for e in evs:
        if e["Hour"] <= since or ip not in (e.get("SrcIpAddr"), e.get("DstIpAddr")):
            continue
        if e.get("EventSchema") != "NetworkSession" and not e.get("DstIpAddr"):
            continue
        k = (e["SourceGroup"], e["SrcIpAddr"], e["DstIpAddr"], e.get("DstPortNumber"))
        a = agg.setdefault(k, {"SourceGroup": k[0], "SrcIpAddr": k[1], "DstIpAddr": k[2], "DstPortNumber": k[3],
                               "Sessions": 0, "FirstSeen": e["FirstSeen"], "LastSeen": e["LastSeen"],
                               "Actions": set(), "Results": set()})
        a["Sessions"] += int(e["Count"])
        a["FirstSeen"] = min(a["FirstSeen"], e["FirstSeen"]); a["LastSeen"] = max(a["LastSeen"], e["LastSeen"])
        if e.get("DvcAction"):
            a["Actions"].add(e["DvcAction"])
        if e.get("EventResult"):
            a["Results"].add(e["EventResult"])
    return [{**a, "FirstSeen": _iso(a["FirstSeen"]), "LastSeen": _iso(a["LastSeen"]),
             "Actions": sorted(a["Actions"]), "Results": sorted(a["Results"])}
            for a in sorted(agg.values(), key=lambda x: -x["Sessions"])][:500]


def _by_key(rows: list[dict]) -> dict[tuple, list[dict]]:
    """Rollup rows by (group, sample key): rows that share a sample key came from the same event."""
    idx: dict[tuple, list[dict]] = defaultdict(list)
    for e in rows:
        for k in e["SampleKeys"] or []:
            idx[(e["SourceGroup"], k)].append(e)
    return idx


def timeline(ents: list[dict], value: str, days: float = 7) -> list[dict]:
    """One point per HuntEntity row that holds the value (an hour of one source, role and result),
    oldest first. Entities lists other values seen in the same sampled events."""
    v, short = value_forms(value)
    rows = _rows(ents, _since(days))
    hits = [e for e in rows if _match(e, v, short)]
    idx = _by_key(rows)
    out = []
    for e in sorted(hits, key=lambda x: (x["FirstSeen"], x["SourceGroup"])):
        others = {f"{o['EntityType']}:{o['Role']}={o['Value']}" for k in e["SampleKeys"] or []
                  for o in idx[(e["SourceGroup"], k)] if not _match(o, v, short)}
        out.append({"EventStartTime": _iso(e["FirstSeen"]), "LastSeen": _iso(e["LastSeen"]), "Count": int(e["Count"]),
                    "SourceTable": e["SourceTable"], "SourceGroup": e["SourceGroup"], "EventType": e["EventType"],
                    "EventResult": e["EventResult"], "MatchedAs": f"{e['EntityType']}:{e['Role']}",
                    "Tier": e["MappingTier"], "Value": e["Value"], "Entities": sorted(others),
                    "SampleKeys": list(e["SampleKeys"] or []),
                    "SourceRecordKey": (e["SampleKeys"] or [""])[0]})
    return out


def related(ents: list[dict], value: str, days: float = 7, limit: int = 25) -> list[dict]:
    """Other entities that share a sampled event with the value: the next things to pivot on.
    Events counts the shared sample events, so it is a lower bound."""
    v, short = value_forms(value)
    rows = _rows(ents, _since(days))
    keys = {(e["SourceGroup"], k) for e in rows if _match(e, v, short) for k in e["SampleKeys"] or []}
    agg: dict[tuple, dict] = {}
    for e in rows:
        if _match(e, v, short):
            continue
        shared = {(e["SourceGroup"], k) for k in e["SampleKeys"] or []} & keys
        if not shared:
            continue
        k = (e["EntityType"], e["ValueNorm"])
        a = agg.setdefault(k, {"EntityType": k[0], "Value": e["ValueNorm"], "_keys": set(), "Sources": set(), "Roles": set()})
        a["_keys"] |= shared; a["Sources"].add(e["SourceGroup"]); a["Roles"].add(e["Role"])
    out = [{"EntityType": a["EntityType"], "Value": a["Value"], "Events": len(a["_keys"]),
            "Sources": sorted(a["Sources"]), "Roles": sorted(a["Roles"])} for a in agg.values()]
    return sorted(out, key=lambda x: (-len(x["Sources"]), -x["Events"], x["Value"]))[:limit]
