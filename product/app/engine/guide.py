"""Decision guide for the field review screen.

Turns field inventory rows and mined templates into decisions an operator can make with a
click: a recommended option with the reason, the common alternatives in plain words, and the
evidence (sample values, value class, fill rate). Choosing an entity and a role picks the ASIM
field name automatically; operators only override it when they know better.
Also builds a draft registry group from the decisions.
"""
from __future__ import annotations

import ipaddress
import re
from collections import Counter
from typing import Any

from app.engine.miner import squash

# ---------------------------------------------------------------- vocab for the screen
ENTITY_CHOICES = [
    {"value": "ip", "label": "IP address"},
    {"value": "user", "label": "User or account"},
    {"value": "host", "label": "Host or device name"},
    {"value": "url", "label": "URL"},
    {"value": "domain", "label": "Domain name"},
    {"value": "hash", "label": "File hash"},
    {"value": "email", "label": "Email address"},
    {"value": "", "label": "Not an entity (skip)"},
]

ROLE_CHOICES = {
    "ip": [
        {"value": "Src", "label": "Source", "help": "Where the connection or sign-in came from"},
        {"value": "Dst", "label": "Destination", "help": "Where it was going"},
        {"value": "Dvc", "label": "Reporting device", "help": "The firewall, server or appliance that wrote the log"},
        {"value": "Unknown", "label": "Not sure", "help": "Still searchable by value; no direction is claimed"},
    ],
    "user": [
        {"value": "Target", "label": "Account signing in / acted on", "help": "In sign-in logs the account signing in is the target"},
        {"value": "Actor", "label": "Who did it", "help": "The account that performed an admin or audit action"},
        {"value": "Src", "label": "User behind the traffic", "help": "Firewall and proxy logs: the user of the source machine"},
        {"value": "Unknown", "label": "Not sure", "help": "Still searchable by value; no role is claimed"},
    ],
    "host": [
        {"value": "Dvc", "label": "Reporting device", "help": "The machine or appliance that wrote the log"},
        {"value": "Src", "label": "Source machine", "help": "The machine the activity came from"},
        {"value": "Dst", "label": "Destination machine", "help": "The machine the activity went to"},
        {"value": "Unknown", "label": "Not sure", "help": "Still searchable by value"},
    ],
}
DEFAULT_ROLES = [{"value": "Unknown", "label": "No role", "help": "URLs, domains and hashes are searched by value"}]

ASIM_BY_ENTITY_ROLE = {
    ("ip", "Src"): "SrcIpAddr", ("ip", "Dst"): "DstIpAddr", ("ip", "Dvc"): "DvcIpAddr",
    ("user", "Actor"): "ActorUsername", ("user", "Target"): "TargetUsername",
    ("user", "Src"): "SrcUsername", ("user", "Dst"): "DstUsername",
    ("host", "Src"): "SrcHostname", ("host", "Dst"): "DstHostname", ("host", "Dvc"): "DvcHostname",
    ("url", "Unknown"): "Url", ("domain", "Unknown"): "DstDomain", ("hash", "Unknown"): "FileSHA256",
}
NON_ENTITY_ASIM = {"srcport": "SrcPortNumber", "sourceport": "SrcPortNumber", "sport": "SrcPortNumber",
                   "dstport": "DstPortNumber", "destinationport": "DstPortNumber", "dport": "DstPortNumber",
                   "port": "DstPortNumber", "protocol": "NetworkProtocol", "proto": "NetworkProtocol",
                   "action": "DvcAction", "deviceaction": "DvcAction", "useragent": "HttpUserAgent",
                   "httpuseragent": "HttpUserAgent", "severity": "EventSeverity"}

PRESETS = {
    "authentication": {"label": "Sign-in log", "schema": "Authentication", "event_type": "Logon",
                       "user_role": "Target", "lone_ip_role": "Src",
                       "hint": "VPN, SSO, identity provider, SSH or console sign-ins"},
    "network": {"label": "Firewall or network session", "schema": "NetworkSession", "event_type": "NetworkSession",
                "user_role": "Src", "lone_ip_role": "Unknown",
                "hint": "Firewalls, NAT, flow logs: two IPs, ports and an action"},
    "web": {"label": "Web proxy or WAF", "schema": "WebSession", "event_type": "HTTPsession",
            "user_role": "Src", "lone_ip_role": "Src", "hint": "Proxies, secure web gateways, WAFs"},
    "audit": {"label": "Admin or audit activity", "schema": "AuditEvent", "event_type": "",
              "user_role": "Actor", "lone_ip_role": "Src", "hint": "Configuration changes, app audit trails"},
    "physical": {"label": "Physical access", "schema": "", "event_type": "PhysicalAccess",
                 "user_role": "Actor", "lone_ip_role": "Dvc", "hint": "Badge readers, door controllers"},
    "other": {"label": "Something else", "schema": "", "event_type": "", "user_role": "Unknown",
              "lone_ip_role": "Unknown", "hint": "Index the entities with no schema"},
}

ROLE_TOKENS = {
    "Src": ["src", "source", "client", "orig", "caller", "from", "remote"],
    "Dst": ["dst", "dest", "destination", "server", "resp", "to", "target"],
    "Dvc": ["dvc", "device", "reporter", "observer", "sensor", "reader", "computer", "host", "appliance"],
    "Actor": ["actor", "initiator", "admin", "operator", "caller", "holder", "by"],
    "Target": ["target", "member", "affected", "subject", "account", "login", "upn"],
}
RESULT_NAMES = {"result", "outcome", "status", "action", "auth", "resulttype", "deviceaction", "disposition",
                "originaloutcomeresult", "consolelogin"}
TYPE_NAMES = {"operation", "eventname", "eventtype", "activity", "action", "op", "category", "eventoriginaltype"}
ID_NAMES = {"id", "eventid", "uid", "uuid", "recordid", "awseventid", "eventoriginaluid", "requestid", "correlationid"}


def _tokens_role(name: str, entity: str) -> str | None:
    s = squash(name.split(".")[-1])
    allowed = {r["value"] for r in ROLE_CHOICES.get(entity, [])}
    for role in ("Src", "Dst", "Actor", "Target", "Dvc"):
        if role in allowed and any(s.startswith(t) or s.endswith(t) or t in s for t in ROLE_TOKENS[role]):
            return role
    return None


def _private_share(samples: list[str]) -> float:
    n = p = 0
    for s in samples:
        m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", s or "")
        if not m:
            continue
        try:
            n += 1
            p += ipaddress.IPv4Address(m.group(1)).is_private
        except ValueError:
            pass
    return p / n if n else 0.0


def recommend(field: dict, preset: str, peers: list[dict]) -> dict:
    """One decision card for one inventory row."""
    p = PRESETS.get(preset, PRESETS["other"])
    name, entity = field["field"], field.get("proposedEntity", "")
    evidence = [f"{round(field['fillRate'] * 100)}% of rows have a value"]
    if field.get("valueClass"):
        evidence.append(f"{round(field['valueClassShare'] * 100)}% of values look like {field['valueClass'].replace('_', ' ')}")
    sq = squash(name.split(".")[-1])
    card: dict[str, Any] = {"field": name, "kind": field["kind"], "samples": field.get("samples", []),
                            "fillRate": field["fillRate"], "evidence": evidence}

    # result and event type candidates (small sets of repeated values)
    distinct = len(set(field.get("samples", [])))
    if sq in RESULT_NAMES and field["fillRate"] > 0.5 and not entity:
        card.update(decision="result", recommended={"use": "result"}, confidence="high" if sq in ("result", "outcome") else "medium",
                    reason="Name and values look like an outcome; map each value to Success or Failure")
        return card
    if sq in TYPE_NAMES and not entity and distinct <= 5:
        card.update(decision="event_type", recommended={"use": "event_type"}, confidence="medium",
                    reason="A short list of repeated values that name the activity")
        return card
    if sq in ID_NAMES and not entity:
        card.update(decision="record_key", recommended={"use": "record_key"}, confidence="medium",
                    reason="Looks like a unique event ID: use it to pivot back to the raw row")
        return card
    if not entity:
        asim = NON_ENTITY_ASIM.get(sq) or field.get("proposedAsim", "")
        if asim and field["fillRate"] > 0.3:
            card.update(decision="field", recommended={"entity": "", "role": "", "asim": asim}, confidence="medium",
                        reason=f"Not an entity, but ASIM has a field for it ({asim})")
        else:
            card.update(decision="skip", recommended={"entity": "", "role": "", "asim": ""}, confidence="high",
                        reason="No entity-like values; leave it in the raw table")
        return card

    # entity fields: pick a role
    role, why = _tokens_role(name, entity), ""
    role_from_name = bool(role)
    if role:
        why = f"the field name suggests '{next(c['label'] for c in ROLE_CHOICES[entity] if c['value'] == role)}'"
    elif entity == "user":
        role, why = p["user_role"], f"for a {p['label'].lower()}, the main account is usually the {p['user_role'].lower()}"
    elif entity == "ip":
        same = [f for f in peers if f.get("proposedEntity") == "ip" and f["field"] != name]
        if not same:
            role, why = p["lone_ip_role"], f"the only IP field in a {p['label'].lower()}"
        else:
            priv = _private_share(field.get("samples", []))
            role = "Unknown"
            why = (f"{len(same) + 1} IP fields and no direction in the name "
                   f"({round(priv * 100)}% of samples are private addresses); check one sample row")
    elif entity == "host":
        role, why = "Dvc", "a host name with no direction is usually the reporting device"
    else:
        role, why = "Unknown", "searched by value"
    share = field.get("valueClassShare", 0)
    if role == "Unknown" and entity in ("ip", "user", "host"):
        confidence = "low"
    elif role_from_name and share >= 0.9:
        confidence = "high"
    elif share >= 0.9:
        confidence = "medium"
    else:
        confidence = "low"
    asim = ASIM_BY_ENTITY_ROLE.get((entity, role), "")
    label = next((c["label"] for c in ENTITY_CHOICES if c["value"] == entity), entity)
    card.update(decision="entity", recommended={"entity": entity, "role": role, "asim": asim}, confidence=confidence,
                reason=f"{label}: {why}", roleChoices=ROLE_CHOICES.get(entity, DEFAULT_ROLES))
    return card


def result_values(rows: list[dict], getter, vocab: dict) -> list[dict]:
    """Distinct values of a result field with a suggested outcome for each."""
    counts = Counter(getter(r) for r in rows)
    v = vocab["result_vocab"]["default"]
    out = []
    for value, n in counts.most_common(20):
        low = (value or "").strip().lower()
        sug = next((o for o in ("Success", "Failure", "Partial") if low in [str(w) for w in v.get(o, [])]), "")
        if not sug and low in ("granted", "ok", "0", "permitted"):
            sug = "Success"
        if not sug and low in ("denied", "fail", "refused", "locked"):
            sug = "Failure"
        out.append({"value": value, "rows": n, "suggested": sug or "Ignore"})
    return out


def template_card(t: dict, preset: str) -> dict:
    """Decision card for a mined template: suggested outcome and slot names."""
    p = PRESETS.get(preset, PRESETS["other"])
    low = t["template"].lower()
    outcome = ("Failure" if re.search(r"\b(fail|failed|invalid|denied|refused|error)\b", low) else
               "Success" if re.search(r"\b(accepted|success|ok|opened|granted|allowed)\b", low) else "")
    slots = []
    for i, tok in enumerate(t.get("tokens", []), start=1):
        if tok == "<IP>":
            sug = {"entity": "ip", "role": p["lone_ip_role"] if p["lone_ip_role"] != "Unknown" else "Src"}
        elif tok == "<EMAIL>":
            sug = {"entity": "user", "role": p["user_role"]}
        elif tok == "<NUM>":
            sug = {"entity": "", "role": "", "asim": "SrcPortNumber" if "port" in low else ""}
        else:
            sug = {"entity": "", "role": ""}
        sug.setdefault("asim", ASIM_BY_ENTITY_ROLE.get((sug["entity"], sug["role"]), ""))
        slots.append({"slot": f"slot{i}", "token": tok, "recommended": sug})
    # a word right before " from <IP>" or "for <word>" is usually the user
    m = re.search(r"\bfor (?:invalid user )?(\S+) from", t["example"])
    return {**t, "outcomeSuggested": outcome, "eventTypeSuggested": p["event_type"], "slots": slots,
            "userHint": m.group(1) if m else ""}


# ---------------------------------------------------------------- draft builder
def build_group(table: str, decisions: dict, sample_columns: list[str]) -> dict:
    """Registry group from the operator's decisions.

    decisions = {
      "id", "preset", "vendor", "product",
      "fields": [{"field", "kind", "entity", "role", "asim"}],
      "result": {"field", "kind", "map": {value: outcome}} | None,
      "event_type": {"field", "kind", "map": {...}} | {"constant": ...} | None,
      "record_key": {"field", "kind"} | None,
      "templates": [{"id", "match", "regex", "event_type", "event_result", "slots": {name: {entity, role}}}],
      "text_column": str | None,
    }
    """
    p = PRESETS.get(decisions.get("preset", "other"), PRESETS["other"])
    gid = decisions.get("id") or f"{table}:main"
    g: dict[str, Any] = {"id": gid, "table": table, "filter": "true", "spark_filter": "true",
                         "vendor": decisions.get("vendor", ""), "product": decisions.get("product", ""),
                         "schema": p["schema"], "status": "approved" if decisions.get("engine") == "kql_job" else "proposed",
                         "layer": "registry", "tier": 1}
    text = decisions.get("text_column")
    kv_fields = [f for f in decisions.get("fields", []) if f.get("kind") == "kv" and f.get("entity") or
                 f.get("kind") == "kv" and f.get("asim")]
    rules = []
    for f in decisions.get("fields", []):
        if f.get("kind") == "kv":
            continue
        if not (f.get("entity") or f.get("asim")):
            continue
        r = _rule(f)
        if f.get("entity"):
            r.update(entity=f["entity"], role=f.get("role") or "Unknown")
        if f.get("asim"):
            r["asim"] = f["asim"]
        rules.append(r)
    if rules:
        g["fields"] = rules

    res = decisions.get("result")
    if res and res.get("kind") != "kv":
        g["result"] = {**_rule(res), "map": {k: v for k, v in (res.get("map") or {}).items() if v in ("Success", "Failure", "Partial")},
                       "default": "NA"}
    et = decisions.get("event_type")
    if et and et.get("constant"):
        g["event_type"] = {"constant": et["constant"]}
    elif et and et.get("field"):
        g["event_type"] = {**_rule(et), "map": et.get("map") or {}, "default": et.get("default", "Other")} \
            if et.get("map") else _rule(et)
    elif p["event_type"]:
        g["event_type"] = {"constant": p["event_type"]}

    rk = decisions.get("record_key")
    if rk and rk.get("kind") == "json":
        g["record_key_path"] = rk["field"]
    elif rk and rk.get("field"):
        g["record_key_fields"] = [rk["field"]]
    else:
        g["record_key_fields"] = [c for c in sample_columns if c not in ("TimeGenerated", "TenantId", "Type")][:6]

    templates = list(decisions.get("templates") or [])
    if text and kv_fields:
        templates += kv_templates(text, kv_fields, res if res and res.get("kind") == "kv" else None,
                                  g.get("event_type", {}).get("constant", ""))
    if text:
        g["text_column"] = text
        g["layer"] = "template"
        g["templates"] = templates
        g["filter"] = f"isnotempty({text})"
        g["spark_filter"] = f"{text} IS NOT NULL AND {text} <> ''"
    if not rules and not text:
        raise ValueError("Pick at least one field or template")
    return g


def _rule(f: dict) -> dict:
    if f.get("kind") == "json":
        return {"path": f["field"]}
    return {"column": f["field"]}


def kv_templates(text: str, fields: list[dict], result: dict | None, event_type: str) -> list[dict]:
    """key=value sources: one template per mapped result value (or one overall), with a named
    group for each chosen key in the order the keys appear."""
    keys = [f["field"].split(".", 1)[1] for f in fields]
    names, slots = [], {}
    for f, k in zip(fields, keys):
        asim = f.get("asim") or ASIM_BY_ENTITY_ROLE.get((f.get("entity"), f.get("role") or "Unknown")) or re.sub(r"\W", "", k)
        base, i = asim, 2
        while asim in names:
            asim, i = f"{base}{i}", i + 1
        names.append(asim)
        slots[asim] = {"entity": f["entity"], "role": f.get("role") or "Unknown"} if f.get("entity") else {}
    body = ".*?".join(f"{re.escape(k)}=(?P<{n}>[^\\s;|,]+)" for k, n in zip(keys, names))
    out = []
    if result and result.get("map"):
        rkey = result["field"].split(".", 1)[1]
        for value, outcome in result["map"].items():
            if outcome not in ("Success", "Failure", "Partial"):
                continue
            out.append({"id": f"kv-{rkey}-{re.sub(r'[^a-z0-9]+', '-', str(value).lower())}",
                        "match": f"{rkey}={value}", "regex": body, "event_type": event_type,
                        "event_result": outcome, "tier": 1, "slots": slots})
    else:
        out.append({"id": "kv-main", "match": f"{keys[0]}=", "regex": body, "event_type": event_type,
                    "event_result": "", "tier": 1, "slots": slots})
    return out
