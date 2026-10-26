"""Generate lake-safe KQL from the grammar-group registry.

Outputs (under --out, default ./out):
  kql_jobs/<group>.entity.kql   KQL job query that appends to the HuntEntity table
  kql_jobs/<group>.event.kql    KQL job query that appends to the HuntEvent table (Tier 1 groups only)
  notebook/notebook_config.json Config for the notebooks: every group (02 indexes engine: notebook
                                groups; 03 measures coverage for all of them)
  mcp_tools/*.kql               Queries for the MCP tools (see ../mcp/tools.yaml)

Every query is plain KQL: no stored functions, no ASIM parser calls, so it runs in
lake KQL and KQL jobs. Usage:
  python generate.py --registry ../registry/groups.example.yaml --vocab ../registry/vocab.yaml
"""
from __future__ import annotations

import argparse
import json
import os
import re
from typing import Any

import yaml

# ---------------------------------------------------------------- output schemas
# Both tables are appended to by many jobs, so every query projects every column
# in this order (KQL jobs fail when an append does not match the table schema).
ENTITY_COLUMNS = [
    ("EventStartTime", "datetime"), ("SourceTable", "string"), ("SourceGroup", "string"),
    ("SourceRecordKey", "string"), ("EventVendor", "string"), ("EventProduct", "string"),
    ("EventSchema", "string"), ("EventType", "string"), ("EventResult", "string"),
    ("EntityType", "string"), ("Role", "string"), ("Value", "string"), ("ValueNorm", "string"),
    ("ValueType", "string"), ("MappingLayer", "string"), ("MappingTier", "int"),
]
EVENT_COLUMNS = [
    ("EventStartTime", "datetime"), ("SourceTable", "string"), ("SourceGroup", "string"),
    ("SourceRecordKey", "string"), ("EventVendor", "string"), ("EventProduct", "string"),
    ("EventSchema", "string"), ("EventType", "string"), ("EventResult", "string"),
    ("EventResultDetails", "string"), ("EventSeverity", "string"),
    ("SrcIpAddr", "string"), ("SrcPortNumber", "int"), ("DstIpAddr", "string"), ("DstPortNumber", "int"),
    ("NetworkProtocol", "string"), ("DvcAction", "string"), ("SrcHostname", "string"),
    ("DstHostname", "string"), ("DvcHostname", "string"), ("DvcIpAddr", "string"), ("DvcDomain", "string"),
    ("SrcUsername", "string"), ("DstUsername", "string"),
    ("ActorUsername", "string"), ("ActorUsernameType", "string"), ("ActorUserId", "string"),
    ("ActorUserIdType", "string"), ("TargetUsername", "string"), ("TargetUsernameType", "string"),
    ("Url", "string"), ("DstDomain", "string"), ("HttpUserAgent", "string"), ("DnsQuery", "string"),
    ("FileName", "string"), ("FileSHA256", "string"), ("FileMD5", "string"),
    ("ActingProcessName", "string"), ("TargetProcessName", "string"), ("TargetProcessCommandLine", "string"),
    ("DstZone", "string"), ("MappingTier", "int"),
]
NULL_OF = {"string": '""', "int": "int(null)", "datetime": "datetime(null)"}
CAST_OF = {"string": "tostring", "int": "toint", "datetime": "todatetime"}

ASIM_OUTPUT_FIELDS = [
    {"column": "SrcIpAddr", "asim": "SrcIpAddr", "entity": "ip", "role": "Src"},
    {"column": "DstIpAddr", "asim": "DstIpAddr", "entity": "ip", "role": "Dst"},
    {"column": "DvcIpAddr", "asim": "DvcIpAddr", "entity": "ip", "role": "Dvc"},
    {"column": "SrcHostname", "asim": "SrcHostname", "entity": "host", "role": "Src"},
    {"column": "DstHostname", "asim": "DstHostname", "entity": "host", "role": "Dst"},
    {"column": "DvcHostname", "asim": "DvcHostname", "entity": "host", "role": "Dvc"},
    {"column": "ActorUsername", "asim": "ActorUsername", "entity": "user", "role": "Actor"},
    {"column": "TargetUsername", "asim": "TargetUsername", "entity": "user", "role": "Target"},
    {"column": "SrcUsername", "asim": "SrcUsername", "entity": "user", "role": "Src"},
    {"column": "DstUsername", "asim": "DstUsername", "entity": "user", "role": "Dst"},
    {"column": "Url", "asim": "Url", "entity": "url", "role": "Unknown"},
    {"column": "FileSHA256", "asim": "FileSHA256", "entity": "hash", "role": "Unknown"},
]
"""Entity rules for a group whose source_query is an expanded ASIM parser: the parser already
produced ASIM columns, so the mapping is fixed. Columns the parser does not output must be
removed from the group before generating (the KQL checker reports them)."""

ENTITY_TYPES = {"ip", "host", "user", "hash", "url", "domain", "email", "process", "file"}
ROLES = {"Src", "Dst", "Actor", "Target", "Dvc", "Unknown"}

# ---------------------------------------------------------------- KQL helpers

def q(s: str) -> str:
    """KQL double-quoted string literal."""
    s = str(s)
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def rx(s: str) -> str:
    """KQL verbatim string for a regex. Verbatim strings cannot hold a double quote."""
    if '"' in s:
        raise ValueError(f"regex may not contain a double quote: {s}")
    return '@"' + s + '"'


def numbered_regex(regex: str) -> tuple[str, dict[str, int]]:
    """Turn (?P<name>...) groups into plain numbered groups and return name -> index."""
    compiled = re.compile(regex)  # validates the regex and gives group indexes
    plain = re.sub(r"\(\?P<[A-Za-z_][A-Za-z0-9_]*>", "(", regex)
    return plain, dict(compiled.groupindex)


def value_expr(rule: dict) -> str:
    """KQL expression for a field rule: a column, or a path into a dynamic column."""
    if "column" in rule:
        expr = f"tostring({rule['column']})"
        if "when_label" in rule:
            lab = rule["when_label"]
            expr = f"iff({lab['column']} == {q(lab['equals'])}, {expr}, \"\")"
        return expr
    if "path" in rule:
        head, *rest = rule["path"].split(".")
        # parse_json(tostring(x)) works whether the column is dynamic or a JSON string; set
        # json_string: false on a rule to read a dynamic column directly.
        dyn = head if rule.get("json_string") is False else f"parse_json(tostring({head}))"
        return f"tostring({dyn}{''.join('.' + p for p in rest)})"
    raise ValueError(f"field rule needs column or path: {rule}")


def map_expr(rule: dict) -> str:
    """A lookup from source values to ASIM values, e.g. EventID 4625 -> Failure."""
    src = value_expr(rule)
    pairs = ", ".join(f"{src} == {q(k)}, {q(v)}" for k, v in rule["map"].items())
    return f'case({pairs}, {q(rule.get("default", ""))})'


def event_type_expr(group: dict) -> str:
    rule = group.get("event_type")
    if not rule:
        return '""'
    if "constant" in rule:
        return q(rule["constant"])
    if "map" in rule:
        return map_expr(rule)
    return value_expr(rule)


NORMALIZE_TAIL = r'''| extend Value = trim(@"\s+", replace_string(replace_string(Value, '"', ""), "'", ""))
| where tolower(Value) !in (NULLS)
| extend Value = iff(EntityType in ("url", "domain"), replace_string(replace_string(replace_string(Value, "hxxp", "http"), "[.]", "."), "[:]", ":"), Value)
| extend ValueType = case(
    EntityType == "ip", iff(countof(Value, ":") >= 2, "IPv6", "IPv4"),
    EntityType == "user", case(
        Value matches regex @"^S-1-\d+(-\d+)+$", "SID",
        Value matches regex @"^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$", "AADID",
        Value contains @"\", "Windows",
        Value startswith "CN=", "DN",
        Value matches regex @"^[^@\s]+@[^@\s]+\.[^@\s]+$", "UPN",
        "Simple"),
    EntityType == "host", iff(Value contains ".", "FQDN", "Hostname"),
    EntityType == "hash", case(strlen(Value) == 32, "MD5", strlen(Value) == 40, "SHA1", strlen(Value) == 64, "SHA256", "Other"),
    EntityType == "url", "URL",
    EntityType == "email", "UPN",
    EntityType == "domain", "FQDN",
    "Other")
| extend ValueNorm = case(
    ValueType == "IPv4", extract(@"(\d{1,3}(?:\.\d{1,3}){3})", 1, Value),
    ValueType == "IPv6", tolower(trim(@"[\[\]]", tostring(split(Value, "%")[0]))),
    ValueType in ("SID", "AADID"), toupper(Value),
    ValueType == "Windows", tolower(tostring(split(Value, @"\")[1])),
    ValueType == "DN", tolower(extract(@"^CN=([^,]+)", 1, Value)),
    EntityType == "user" and ValueType == "UPN", tolower(tostring(split(Value, "@")[0])),
    EntityType == "host" and Value contains @"\", tolower(tostring(split(Value, @"\")[1])),
    EntityType == "host" and ValueType == "FQDN", tolower(tostring(split(Value, ".")[0])),
    EntityType == "domain", tolower(trim_end(@"\.", Value)),
    tolower(Value))
| where not(ValueType == "IPv4" and isnull(parse_ipv4(ValueNorm)))
| where not(EntityType == "host" and isnotnull(parse_ipv4(Value)))
| where not(EntityType == "hash" and ValueType == "Other")
| where isnotempty(ValueNorm)'''

CLASSIFIER = [
    # (EntityType, regex with one capture group)
    ("ip", r"(?:^|[^\w.:])(\d{1,3}(?:\.\d{1,3}){3})(?:[^\w.]|$)"),
    ("hash", r"\b([a-fA-F0-9]{64}|[a-fA-F0-9]{40})\b"),
    ("url", r"(https?://[^\s'<>]+)"),
    ("email", r"\b([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\b"),
]


def complete_group(group: dict) -> dict:
    """Fill record_key / spark_record_key from record_key_fields or record_key_path, so KQL,
    Spark and Python compute the same SourceRecordKey from one definition."""
    g = dict(group)
    tc = g.get("time_column", "TimeGenerated")
    if g.get("record_key_path") and not g.get("record_key"):
        head, *rest = g["record_key_path"].split(".")
        g["record_key"] = f"tostring({head}{''.join('.' + p for p in rest)})"
        g["spark_record_key"] = f"get_json_object({head}, '$.{'.'.join(rest)}')"
    elif g.get("record_key_fields") and not g.get("record_key"):
        cols = g["record_key_fields"]
        g["record_key"] = ('hash_sha256(strcat(format_datetime(' + tc + ', "yyyy-MM-dd HH:mm:ss.fff")'
                           + "".join(f', "|", tostring({c})' for c in cols) + "))")
        g["spark_record_key"] = ("sha2(concat_ws('|', date_format(" + tc + ", 'yyyy-MM-dd HH:mm:ss.SSS')"
                                 + "".join(f", coalesce(cast({c} as string), '')" for c in cols) + "), 256)")
    if not g.get("record_key"):
        raise ValueError(f"group {g.get('id')} needs record_key, record_key_fields or record_key_path")
    # exclude_text: lines an operator marked as noise (heartbeats, keepalives) on the text column
    ex = [x for x in g.get("exclude_text") or [] if x]
    if ex and g.get("text_column") and not g.get("_excluded"):
        col = g["text_column"]
        g["filter"] = f"({g.get('filter', 'true')})" + "".join(f" and not({col} contains {q(x)})" for x in ex)
        g["spark_filter"] = f"({g.get('spark_filter', 'true')})" + "".join(
            f" AND NOT ({col} LIKE '%" + x.replace("'", "''").replace("%", "\\%").replace("_", "\\_") + "%')" for x in ex)
        g["_excluded"] = True
    return g


def header(group: dict, defaults: dict) -> str:
    d = group.get("delay", defaults.get("delay", "15m"))
    w = group.get("window", defaults.get("window", "1h"))
    tc = group.get("time_column", "TimeGenerated")
    return (
        f"// Generated by generate.py from registry group {group['id']}. Do not edit by hand.\n"
        f"let endTime = bin(now() - {d}, {w});\n"
        f"let startTime = endTime - {w};\n"
        + (f"let _source = () {{\n{group['source_query'].strip().rstrip(';')}\n}};\nlet base = _source()\n"
           if group.get("source_query")
           else f"let base = {group['table']}\n") +
        f"| where {tc} >= startTime and {tc} < endTime\n"
        f"| where {group.get('filter', 'true')}\n"
        f"| extend SourceRecordKey = tostring({group['record_key']}), EventStartTime = todatetime({tc});\n"
    )


def entity_bag(entity: str, role: str, value: str, layer: str, tier: int) -> str:
    if entity not in ENTITY_TYPES:
        raise ValueError(f"unknown entity type {entity}")
    if role not in ROLES:
        raise ValueError(f"unknown role {role}")
    return (f'bag_pack("EntityType", {q(entity)}, "Role", {q(role)}, "Value", {value}, '
            f'"MappingLayer", {q(layer)}, "MappingTier", {tier})')


def entity_projection(group: dict, event_type: str, event_result: str) -> str:
    return (
        "| mv-expand _e = _ents\n"
        f"| extend SourceTable = {q(group['table'])}, SourceGroup = {q(group['id'])},\n"
        f"         EventVendor = {q(group.get('vendor', ''))}, EventProduct = {q(group.get('product', ''))},\n"
        f"         EventSchema = {q(group.get('schema', ''))}, EventType = tostring({event_type}), EventResult = tostring({event_result}),\n"
        "         EntityType = tostring(_e.EntityType), Role = tostring(_e.Role), Value = tostring(_e.Value),\n"
        "         MappingLayer = tostring(_e.MappingLayer), MappingTier = toint(_e.MappingTier)\n"
    )


def finish_entity(nulls: list[str]) -> str:
    cols = ", ".join(c for c, _ in ENTITY_COLUMNS)
    tail = NORMALIZE_TAIL.replace("NULLS", ", ".join(q(n) for n in nulls))
    return f"{tail}\n| project {cols}"


def result_block(group: dict, vocab: dict) -> tuple[str, str]:
    """Returns (extend line computing _r, case expression) for the group's result rule."""
    rule = group.get("result")
    if not rule:
        return "", '""'
    if "map" in rule:
        return "", map_expr(rule)
    v = vocab["result_vocab"][rule.get("vocab", "default")]
    extend = f"| extend _r = tolower(trim(@\"\\s\", {value_expr(rule)}))\n"
    parts = []
    for outcome in ("Success", "Failure", "Partial"):
        words = ", ".join(q(w) for w in v.get(outcome, []))
        if words:
            parts.append(f"_r in ({words}), {q(outcome)}")
    if v.get("http_status"):
        parts.append('toint(_r) between (100 .. 399), "Success"')
        parts.append('toint(_r) between (400 .. 599), "Failure"')
    return extend, f'case({", ".join(parts)}, "NA")'


def build_entity_query(group: dict, defaults: dict, vocab: dict) -> str:
    nulls = vocab.get("null_values", [])
    tier = int(group.get("tier", 2))
    blocks = []
    const = [entity_bag(c["entity"], c["role"], value_expr(c), "registry", tier)
             for c in group.get("constant_entities", []) if c.get("entity")]

    # Structured fields
    fields = [f for f in group.get("fields", []) if f.get("entity")]
    if fields or (const and not group.get("text_column")):
        r_ext, r_case = result_block(group, vocab)
        bags = [entity_bag(f["entity"], f.get("role", "Unknown"), value_expr(f), "registry", tier) for f in fields]
        blocks.append(
            "base\n" + r_ext +
            f"| extend _ents = pack_array({', '.join(bags + const)})\n" +
            entity_projection(group, event_type_expr(group), r_case)
        )

    # Templates on a text column
    text = group.get("text_column")
    templates = group.get("templates", []) or []
    for t in templates:
        plain, idx = numbered_regex(t["regex"])
        ext = ", ".join(f"{name} = extract({rx(plain)}, {i}, {text})" for name, i in idx.items())
        bags = [entity_bag(s["entity"], s.get("role", "Unknown"), name, "template", int(t.get("tier", tier)))
                for name, s in (t.get("slots") or {}).items() if s and s.get("entity")]
        const_t = [] if fields else [
            entity_bag(c["entity"], c["role"], value_expr(c), "template", int(t.get("tier", tier)))
            for c in group.get("constant_entities", []) if c.get("entity")]
        blocks.append(
            "base\n"
            f"| where {text} contains {q(t['match'])}\n"
            f"| where {text} matches regex {rx(plain)}\n"
            f"| extend {ext}\n"
            f"| extend _ents = pack_array({', '.join(bags + const_t)})\n" +
            entity_projection(group, q(t.get("event_type", "")), q(t.get("event_result", "")))
        )

    # Value classifier on whatever no template matched
    if text:
        unmatched = "base\n"
        if templates:
            conds = " or ".join(f"{text} matches regex {rx(numbered_regex(t['regex'])[0])}" for t in templates)
            unmatched += f"| where not({conds})\n"
        arrays = ", ".join(f"_c{i} = extract_all({rx(r)}, {text})" for i, (_, r) in enumerate(CLASSIFIER))
        unmatched += f"| extend {arrays}\n"
        concat = ", ".join(
            f"iff(isnull(_c{i}), dynamic([]), _c{i})" for i in range(len(CLASSIFIER)))
        types = ", ".join(q(e) for e, _ in CLASSIFIER)
        blocks.append(
            unmatched +
            f"| extend _types = dynamic([{types}]), _vals = pack_array({concat})\n"
            "| mv-expand with_itemindex = _i _v = _vals to typeof(dynamic)\n"
            "| mv-expand _x = _v to typeof(string)\n"
            "| extend _ents = pack_array(bag_pack(\"EntityType\", tostring(_types[_i]), \"Role\", \"Unknown\", "
            "\"Value\", _x, \"MappingLayer\", \"classifier\", \"MappingTier\", 2))\n" +
            entity_projection(group, '""', '""')
        )
        if const and not fields:
            blocks.append(
                unmatched.split("| extend _c0")[0] +
                f"| extend _ents = pack_array({', '.join(const)})\n" +
                entity_projection(group, '""', '""')
            )

    if not blocks:
        raise ValueError(f"group {group['id']} has nothing to map")
    union = "union\n" + ",\n".join("(" + b.rstrip() + "\n)" for b in blocks)
    return header(group, defaults) + union + "\n" + finish_entity(nulls) + "\n"


def build_event_query(group: dict, defaults: dict, vocab: dict) -> str | None:
    """HuntEvent rows for Tier 1 groups with structured field rules."""
    if int(group.get("tier", 2)) != 1 or not group.get("fields"):
        return None
    nulls = ", ".join(q(n) for n in vocab.get("null_values", []))

    def clean(name: str, expr: str) -> str:
        """Null markers become empty; IP columns lose ports and brackets (same rules as HuntEntity)."""
        e = f'iff(tolower(trim(@"\\s", {expr})) in ({nulls}), "", trim(@"\\s", {expr}))'
        if name.endswith("IpAddr"):
            e = (f'iff(countof({e}, ":") >= 2, tolower(trim(@"[\\[\\]]", tostring(split({e}, "%")[0]))), '
                 f'extract(@"(\\d{{1,3}}(?:\\.\\d{{1,3}}){{3}})", 1, {e}))')
        return e

    mapped = {}
    for f in group["fields"]:
        if f.get("asim"):
            mapped[f["asim"]] = clean(f["asim"], value_expr(f))
    for c in group.get("constant_entities", []):
        if c.get("asim"):
            mapped[c["asim"]] = clean(c["asim"], value_expr(c))
    r_ext, r_case = result_block(group, vocab)
    mapped.update({
        "SourceTable": q(group["table"]), "SourceGroup": q(group["id"]),
        "EventVendor": q(group.get("vendor", "")), "EventProduct": q(group.get("product", "")),
        "EventSchema": q(group.get("schema", "")), "EventType": event_type_expr(group),
        "EventResult": r_case, "MappingTier": "1",
    })
    cols = []
    for name, typ in EVENT_COLUMNS:
        if name in ("EventStartTime", "SourceRecordKey"):
            cols.append(name)
        elif name in mapped:
            cols.append(f"{name} = {CAST_OF[typ]}({mapped[name]})")
        else:
            cols.append(f"{name} = {NULL_OF[typ]}")
    return header(group, defaults) + "base\n" + r_ext + "| project " + ",\n    ".join(cols) + "\n"


def notebook_config(groups: list[dict], vocab: dict) -> dict:
    out = []
    for g in (complete_group(x) for x in groups):
        tpl = []
        for t in g.get("templates", []) or []:
            plain, idx = numbered_regex(t["regex"])
            tpl.append({**t, "regex_plain": plain, "group_index": idx})
        out.append({**g, "templates": tpl})
    return {"groups": out, "vocab": vocab, "classifier": CLASSIFIER,
            "entity_columns": ENTITY_COLUMNS, "event_columns": EVENT_COLUMNS}


def slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", required=True)
    ap.add_argument("--vocab", required=True)
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    reg = yaml.safe_load(open(a.registry, encoding="utf-8"))
    vocab = yaml.safe_load(open(a.vocab, encoding="utf-8"))
    defaults = reg.get("defaults", {})
    os.makedirs(os.path.join(a.out, "kql_jobs"), exist_ok=True)
    os.makedirs(os.path.join(a.out, "notebook"), exist_ok=True)
    jobs = 0
    for g in (complete_group(x) for x in reg["groups"]):
        if g.get("engine", "notebook") != "kql_job":
            continue
        name = slug(g["id"])
        with open(os.path.join(a.out, "kql_jobs", f"{name}.entity.kql"), "w", encoding="utf-8") as f:
            f.write(build_entity_query(g, defaults, vocab))
        jobs += 1
        ev = build_event_query(g, defaults, vocab)
        if ev:
            with open(os.path.join(a.out, "kql_jobs", f"{name}.event.kql"), "w", encoding="utf-8") as f:
                f.write(ev)
            jobs += 1
    with open(os.path.join(a.out, "notebook", "notebook_config.json"), "w", encoding="utf-8") as f:
        json.dump(notebook_config(reg["groups"], vocab), f, indent=1)
    print(f"KQL job queries: {jobs} (tenant limit 100 enabled jobs)")
    if jobs > 40:
        print("WARNING: more than 40 KQL jobs; move low-volume groups to engine: notebook")


if __name__ == "__main__":
    main()
