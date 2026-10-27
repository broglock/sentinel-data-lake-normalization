"""Generate lake-safe KQL from the grammar-group registry.

Outputs (under --out, default ./out):
  kql_jobs/<job>.entity.kql     KQL job query that appends to the HuntEntity table: an hourly
                                rollup (one row per hour, source group, entity, role and result)
                                plus job-count rows (EntityType "_stats") for the coverage report
  kql_jobs/<job>.event.kql      KQL job query that appends to the HuntEvent table (Tier 1 only)
  notebook/notebook_config.json Config for the notebooks: every group, with its resolved engine
                                (02 indexes engine: notebook groups; 01 and 03 read the rest)

Engine: a group with status: approved runs in a KQL job; any other group (proposed, not yet
reviewed) runs in notebook 02. Groups are batched into shared jobs by `job` (default: the
source table), so the tenant limit on KQL jobs is counted in tables, not groups.

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
OCC_COLUMNS = [
    ("EventStartTime", "datetime"), ("SourceTable", "string"), ("SourceGroup", "string"),
    ("SourceRecordKey", "string"), ("EventVendor", "string"), ("EventProduct", "string"),
    ("EventSchema", "string"), ("EventType", "string"), ("EventResult", "string"),
    ("EntityType", "string"), ("Role", "string"), ("Value", "string"), ("ValueNorm", "string"),
    ("ValueType", "string"), ("MappingLayer", "string"), ("MappingTier", "int"),
]
"""One row per entity occurrence: the intermediate shape inside every job, before the rollup."""

ROLLUP_KEYS = ["SourceTable", "SourceGroup", "EventVendor", "EventProduct", "EventSchema", "EventType",
               "EventResult", "EntityType", "Role", "ValueNorm", "ValueType", "MappingLayer", "MappingTier"]
SAMPLE_KEYS = 3
ENTITY_COLUMNS = [
    ("Hour", "datetime"), ("FirstSeen", "datetime"), ("LastSeen", "datetime"),
    ("SourceTable", "string"), ("SourceGroup", "string"), ("EventVendor", "string"), ("EventProduct", "string"),
    ("EventSchema", "string"), ("EventType", "string"), ("EventResult", "string"),
    ("EntityType", "string"), ("Role", "string"), ("Value", "string"), ("ValueNorm", "string"),
    ("ValueType", "string"), ("MappingLayer", "string"), ("MappingTier", "int"),
    ("Count", "long"), ("SampleKeys", "dynamic"),
]
"""HuntEntity: one row per hour, source group, entity value, role and result, with a count,
first and last seen times and up to SAMPLE_KEYS record keys for the pivot to raw rows."""

STATS_ROLES = ("RowsRead", "RowsWithEntity", "RowsTemplateMatched")
"""Job-count rows written into HuntEntity with EntityType "_stats" (a KQL job writes one table).
Count = raw rows read, raw rows with at least one entity, raw rows matched by a template.
Notebook 03 builds the coverage report from these rows without reading source tables."""

EVENT_OCC_COLUMNS = [
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
"""One row per Tier 1 event with ASIM columns: the intermediate shape inside every event job."""

EVENT_DROP = ("EventStartTime", "SourceRecordKey", "SrcPortNumber")
EVENT_KEYS = [c for c, _ in EVENT_OCC_COLUMNS if c not in EVENT_DROP]
EVENT_COLUMNS = ([("Hour", "datetime"), ("FirstSeen", "datetime"), ("LastSeen", "datetime")] +
                 [(c, t) for c, t in EVENT_OCC_COLUMNS if c not in EVENT_DROP] +
                 [("Count", "long"), ("SampleKeys", "dynamic")])
"""HuntEvent: one row per hour and unique combination of the mapped ASIM fields (who, from where,
to where, what result), with a count, first and last seen times and up to SAMPLE_KEYS record keys.
Repeated sign-ins and sessions collapse into one row. The source port is left out because it is
different on almost every connection and would stop the rollup from collapsing anything."""
NULL_OF = {"string": '""', "int": "int(null)", "long": "long(null)", "datetime": "datetime(null)",
           "dynamic": "dynamic([])"}
CAST_OF = {"string": "tostring", "int": "toint", "long": "tolong", "datetime": "todatetime",
           "dynamic": "todynamic"}

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


ENTITY_ROLE_ASIM = {(f["entity"], f["role"]): f["asim"] for f in ASIM_OUTPUT_FIELDS if f["role"] != "Unknown"}
ENTITY_ROLE_ASIM.update({("url", "Unknown"): "Url", ("url", "Dst"): "Url", ("domain", "Dst"): "DstDomain",
                         ("domain", "Unknown"): "DstDomain"})
"""HuntEvent column for a template slot, by (entity, role), when the slot names no `asim`."""


def engine_of(group: dict) -> str:
    """approved -> KQL job; anything else (proposed, unreviewed) -> notebook 02. A registry without
    status keys keeps its explicit engine."""
    if "status" in group:
        return "kql_job" if group["status"] == "approved" else "notebook"
    return group.get("engine", "notebook")


def job_of(group: dict) -> str:
    """Jobs are shared per source table unless the group names its own job."""
    return slug(group.get("job") or group["table"])


def fn_name(group: dict) -> str:
    return "G_" + slug(group["id"])


def job_header(groups: list[dict], defaults: dict) -> str:
    g0 = groups[0]
    d = g0.get("delay", defaults.get("delay", "15m"))
    w = g0.get("window", defaults.get("window", "1h"))
    names = ", ".join(g["id"] for g in groups)
    return (f"// Generated by generate.py for registry groups: {names}. Do not edit by hand.\n"
            f"let endTime = bin(now() - {d}, {w});\n"
            f"let startTime = endTime - {w};\n")


def base_block(group: dict) -> str:
    tc = group.get("time_column", "TimeGenerated")
    return (
        (f"let _source = () {{\n{group['source_query'].strip().rstrip(';')}\n}};\nlet base = _source()\n"
         if group.get("source_query") else f"let base = {group['table']}\n") +
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


def finish_occurrences(nulls: list[str]) -> str:
    cols = ", ".join(c for c, _ in OCC_COLUMNS)
    tail = NORMALIZE_TAIL.replace("NULLS", ", ".join(q(n) for n in nulls))
    return f"{tail}\n| project {cols}"


def stats_branch(group: dict, source: str, role: str) -> str:
    """One _stats row per hour: rows read, rows with an entity, rows matched by a template."""
    agg = "Count = dcount(SourceRecordKey)" if role != "RowsRead" else "Count = count()"
    return (f"{source}\n"
            f"| summarize {agg}, FirstSeen = min(EventStartTime), LastSeen = max(EventStartTime)"
            f" by Hour = bin(EventStartTime, 1h)\n"
            f"| extend SourceTable = {q(group['table'])}, SourceGroup = {q(group['id'])}, EntityType = \"_stats\", "
            f"Role = {q(role)}")


ROLLUP = ("occ\n"
          "| summarize Count = count(), FirstSeen = min(EventStartTime), LastSeen = max(EventStartTime),\n"
          f"            SampleKeys = make_set(SourceRecordKey, {SAMPLE_KEYS}), Value = take_any(Value)\n"
          "    by Hour = bin(EventStartTime, 1h), " + ", ".join(ROLLUP_KEYS))


def finish_entity() -> str:
    """Fill the columns stats rows do not carry, then project HuntEntity in table order."""
    cols = []
    for name, typ in ENTITY_COLUMNS:
        if typ == "string":
            cols.append(f"{name} = tostring({name})")
        elif typ == "dynamic":
            cols.append(f"{name} = iff(isnull({name}), dynamic([]), {name})")
        elif name == "MappingTier":
            cols.append(f"{name} = toint({name})")
        else:
            cols.append(name)
    return "| project " + ", ".join(cols)


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


def occurrence_blocks(group: dict, vocab: dict) -> list[str]:
    """The union branches that produce one row per entity occurrence (before normalization)."""
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
    return blocks


def entity_function(group: dict, vocab: dict) -> str:
    """let G_<group> = () { ... }: HuntEntity rollup rows plus _stats rows for one group."""
    nulls = vocab.get("null_values", [])
    blocks = occurrence_blocks(group, vocab)
    union = "union\n" + ",\n".join("(" + b.rstrip() + "\n)" for b in blocks)
    branches = [ROLLUP, stats_branch(group, "base", "RowsRead"), stats_branch(group, "occ", "RowsWithEntity")]
    if group.get("text_column") and group.get("templates"):
        branches.append(stats_branch(group, "occ\n| where MappingLayer == \"template\"", "RowsTemplateMatched"))
    return (f"let {fn_name(group)} = () {{\n" + base_block(group) +
            "let occ = " + union + "\n" + finish_occurrences(nulls) + ";\n"
            "union\n" + ",\n".join("(" + b + "\n)" for b in branches) + "\n};\n")


def build_entity_job(groups: list[dict], defaults: dict, vocab: dict) -> str:
    groups = [complete_group(g) for g in groups]
    return (job_header(groups, defaults) + "".join(entity_function(g, vocab) for g in groups) +
            "union " + ", ".join(f"{fn_name(g)}()" for g in groups) + "\n" + finish_entity() + "\n")


EVENT_ROLLUP = ("| summarize Count = count(), FirstSeen = min(EventStartTime), LastSeen = max(EventStartTime),\n"
                f"            SampleKeys = make_set(SourceRecordKey, {SAMPLE_KEYS})\n"
                "    by Hour = bin(EventStartTime, 1h), " + ", ".join(EVENT_KEYS) + "\n"
                "| project " + ", ".join(c for c, _ in EVENT_COLUMNS) + "\n")


def build_entity_query(group: dict, defaults: dict, vocab: dict) -> str:
    """The HuntEntity job query for a single group (preview, validation, single-group jobs)."""
    return build_entity_job([group], defaults, vocab)




def _clean_event(name: str, expr: str, nulls: str) -> str:
    """Null markers become empty; IP columns lose ports and brackets (same rules as HuntEntity)."""
    e = f'iff(tolower(trim(@"\\s", {expr})) in ({nulls}), "", trim(@"\\s", {expr}))'
    if name.endswith("IpAddr"):
        e = (f'iff(countof({e}, ":") >= 2, tolower(trim(@"[\\[\\]]", tostring(split({e}, "%")[0]))), '
             f'extract(@"(\\d{{1,3}}(?:\\.\\d{{1,3}}){{3}})", 1, {e}))')
    return e


def _event_projection(mapped: dict) -> str:
    cols = []
    for name, typ in EVENT_OCC_COLUMNS:
        if name in ("EventStartTime", "SourceRecordKey"):
            cols.append(name)
        elif name in mapped:
            cols.append(f"{name} = {CAST_OF[typ]}({mapped[name]})")
        else:
            cols.append(f"{name} = {NULL_OF[typ]}")
    return "| project " + ",\n    ".join(cols)


def slot_asim(slot: dict) -> str | None:
    return slot.get("asim") or ENTITY_ROLE_ASIM.get((slot.get("entity"), slot.get("role", "Unknown")))


def event_templates(group: dict) -> list[dict]:
    """Tier 1 templates produce HuntEvent rows too, so text sources answer event questions."""
    if not group.get("text_column"):
        return []
    tier = int(group.get("tier", 2))
    return [t for t in group.get("templates", []) or [] if int(t.get("tier", tier)) == 1]


def has_events(group: dict) -> bool:
    return bool((int(group.get("tier", 2)) == 1 and group.get("fields")) or event_templates(group))


def event_blocks(group: dict, vocab: dict) -> list[str]:
    nulls = ", ".join(q(n) for n in vocab.get("null_values", []))
    common = {"SourceTable": q(group["table"]), "SourceGroup": q(group["id"]),
              "EventVendor": q(group.get("vendor", "")), "EventProduct": q(group.get("product", "")),
              "EventSchema": q(group.get("schema", "")), "MappingTier": "1"}
    consts = {c["asim"]: _clean_event(c["asim"], value_expr(c), nulls)
              for c in group.get("constant_entities", []) if c.get("asim")}
    blocks = []
    if int(group.get("tier", 2)) == 1 and group.get("fields"):
        mapped = {f["asim"]: _clean_event(f["asim"], value_expr(f), nulls) for f in group["fields"] if f.get("asim")}
        mapped.update(consts)
        r_ext, r_case = result_block(group, vocab)
        mapped.update(common, EventType=event_type_expr(group), EventResult=r_case)
        blocks.append("base\n" + r_ext + _event_projection(mapped))
    text = group.get("text_column")
    for t in event_templates(group):
        plain, idx = numbered_regex(t["regex"])
        mapped, ext = dict(consts), []
        for name, slot in (t.get("slots") or {}).items():
            col = slot_asim(slot or {})
            if col and col in dict(EVENT_OCC_COLUMNS) and name in idx:
                ext.append(f"_t_{name} = extract({rx(plain)}, {idx[name]}, {text})")
                mapped[col] = _clean_event(col, f"_t_{name}", nulls)
        mapped.update(common, EventType=q(t.get("event_type", "")), EventResult=q(t.get("event_result", "")))
        blocks.append("base\n"
                      f"| where {text} contains {q(t['match'])}\n"
                      f"| where {text} matches regex {rx(plain)}\n" +
                      (f"| extend {', '.join(ext)}\n" if ext else "") + _event_projection(mapped))
    return blocks


def event_function(group: dict, vocab: dict) -> str | None:
    blocks = event_blocks(group, vocab)
    if not blocks:
        return None
    body = blocks[0] if len(blocks) == 1 else "union\n" + ",\n".join("(" + b + "\n)" for b in blocks)
    return f"let {fn_name(group)}_ev = () {{\n" + base_block(group) + body + "\n};\n"


def build_event_job(groups: list[dict], defaults: dict, vocab: dict) -> str | None:
    """HuntEvent rows: Tier 1 groups with field rules, and Tier 1 templates on text sources."""
    groups = [complete_group(g) for g in groups]
    fns = [(g, event_function(g, vocab)) for g in groups]
    fns = [(g, f) for g, f in fns if f]
    if not fns:
        return None
    return (job_header([g for g, _ in fns], defaults) + "".join(f for _, f in fns) +
            "union " + ", ".join(f"{fn_name(g)}_ev()" for g, _ in fns) + "\n" + EVENT_ROLLUP)


def build_event_query(group: dict, defaults: dict, vocab: dict) -> str | None:
    return build_event_job([group], defaults, vocab)


def plan_jobs(groups: list[dict]) -> dict[str, list[dict]]:
    """Approved groups batched into shared KQL jobs (one per source table unless `job` is set)."""
    jobs: dict[str, list[dict]] = {}
    for g in groups:
        if engine_of(g) == "kql_job":
            jobs.setdefault(job_of(g), []).append(g)
    return jobs


def notebook_config(groups: list[dict], vocab: dict) -> dict:
    out = []
    for g in (complete_group(x) for x in groups):
        tpl = []
        for t in g.get("templates", []) or []:
            plain, idx = numbered_regex(t["regex"])
            tpl.append({**t, "regex_plain": plain, "group_index": idx})
        ev = [{"id": t["id"], "columns": {slot_asim(s or {}): name for name, s in (t.get("slots") or {}).items()
                                           if slot_asim(s or {}) in dict(EVENT_OCC_COLUMNS)}}
              for t in event_templates(g)]
        out.append({**g, "engine": engine_of(g), "templates": tpl, "event_templates": ev})
    return {"groups": out, "vocab": vocab, "classifier": CLASSIFIER, "occ_columns": OCC_COLUMNS,
            "entity_columns": ENTITY_COLUMNS, "event_occ_columns": EVENT_OCC_COLUMNS,
            "event_columns": EVENT_COLUMNS, "event_keys": EVENT_KEYS, "rollup_keys": ROLLUP_KEYS,
            "sample_keys": SAMPLE_KEYS, "stats_roles": list(STATS_ROLES)}


def slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")


def write_jobs(groups: list[dict], defaults: dict, vocab: dict, out: str) -> dict[str, list[str]]:
    """Writes kql_jobs/<job>.entity.kql and .event.kql; returns job file -> group ids."""
    os.makedirs(os.path.join(out, "kql_jobs"), exist_ok=True)
    files = {}
    for job, gs in plan_jobs(groups).items():
        with open(os.path.join(out, "kql_jobs", f"{job}.entity.kql"), "w", encoding="utf-8") as f:
            f.write(build_entity_job(gs, defaults, vocab))
        files[f"{job}.entity.kql"] = [g["id"] for g in gs]
        ev = build_event_job(gs, defaults, vocab)
        if ev:
            with open(os.path.join(out, "kql_jobs", f"{job}.event.kql"), "w", encoding="utf-8") as f:
                f.write(ev)
            files[f"{job}.event.kql"] = [g["id"] for g in gs if has_events(complete_group(g))]
    return files


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", required=True)
    ap.add_argument("--vocab", required=True)
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    reg = yaml.safe_load(open(a.registry, encoding="utf-8"))
    vocab = yaml.safe_load(open(a.vocab, encoding="utf-8"))
    defaults = reg.get("defaults", {})
    files = write_jobs(reg["groups"], defaults, vocab, a.out)
    os.makedirs(os.path.join(a.out, "notebook"), exist_ok=True)
    with open(os.path.join(a.out, "notebook", "notebook_config.json"), "w", encoding="utf-8") as f:
        json.dump(notebook_config(reg["groups"], vocab), f, indent=1)
    nb = [g["id"] for g in reg["groups"] if engine_of(g) == "notebook"]
    print(f"KQL job queries: {len(files)} (tenant limit 100 enabled jobs); notebook 02 groups: {len(nb)}")
    if len(files) > 60:
        print("WARNING: more than 60 KQL jobs; set a shared `job` on related groups")


if __name__ == "__main__":
    main()
