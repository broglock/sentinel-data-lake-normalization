"""Make Microsoft ASIM parser KQL runnable on the Sentinel data lake.

Lake KQL and KQL jobs do not run stored functions. ASIM source parsers are functions
themselves, and most also call helper functions (_ASIM_ResolveFQDN, _ASIM_Lookup*,
_ASIM_GetUsernameType, _ASIM_GetDisabledParsers ...). This tool:

  1. reads a parser YAML (ParserQuery and ParserParams) or a .kql file,
  2. turns the parameters into let statements with their default values,
  3. replaces the helpers it knows with inline KQL,
  4. reports every remaining function call, so you know whether the result is lake-safe.

Usage:
  python asim_expand.py ParserFile.yaml [--out parser.lake.kql]
Exit code 0 = no function calls left (lake-safe), 2 = calls remain (see report).
Check the YAML key names against the current Azure-Sentinel repo before relying on them.
"""
from __future__ import annotations

import argparse
import re
import sys

import yaml

# ---------------------------------------------------------------- helper replacements
FQDN_INLINE = """extend {p}FQDN_in_ = tostring({col})
| extend {p}Hostname = case({p}FQDN_in_ contains @"\\", tostring(split({p}FQDN_in_, @"\\")[1]),
                           {p}FQDN_in_ contains ".", tostring(split({p}FQDN_in_, ".")[0]),
                           {p}FQDN_in_),
         {p}Domain = case({p}FQDN_in_ contains @"\\", tostring(split({p}FQDN_in_, @"\\")[0]),
                         {p}FQDN_in_ contains ".", substring({p}FQDN_in_, indexof({p}FQDN_in_, ".") + 1),
                         ""),
         {p}DomainType = case({p}FQDN_in_ contains @"\\", "Windows", {p}FQDN_in_ contains ".", "FQDN", ""),
         {p}FQDN = iff({p}FQDN_in_ contains "." or {p}FQDN_in_ contains @"\\", {p}FQDN_in_, "")
| project-away {p}FQDN_in_"""

USERNAME_TYPE_INLINE = ('case(isempty({x}), "", {x} contains "@", "UPN", {x} contains @"\\", "Windows", '
                        '{x} startswith "CN=", "DN", "Simple")')

PROTOCOLS = {1: "ICMP", 2: "IGMP", 6: "TCP", 17: "UDP", 41: "IPv6", 47: "GRE", 50: "ESP", 51: "AH", 58: "ICMPv6", 132: "SCTP"}
PROTOCOL_INLINE = "case(" + ", ".join(f"toint({{x}}) == {n}, \"{name}\"" for n, name in PROTOCOLS.items()) + ", tostring({x}))"

FUNC_CALL = re.compile(r"\b(_ASIM_\w+|_Im_\w+|_ASim_\w+|ASim\w+|vim\w+|_GetWatchlist\w*|_ASIM_GetDisabledParsers)\s*\(")


def expand(query: str) -> str:
    out = query
    # invoke _ASIM_Resolve{Src,Dst,Dvc,}FQDN('Column')
    def fqdn(m):
        prefix = {"Src": "Src", "Dst": "Dst", "Dvc": "Dvc", "": ""}[m.group(1)]
        return FQDN_INLINE.format(p=prefix, col=m.group(2))
    out = re.sub(r"invoke\s+_ASIM_Resolve(Src|Dst|Dvc|)FQDN\s*\(\s*['\"]?(\w+)['\"]?\s*\)", fqdn, out)
    out = re.sub(r"_ASIM_GetUsernameType\s*\(\s*([\w.\[\]'\"]+)\s*\)", lambda m: USERNAME_TYPE_INLINE.format(x=m.group(1)), out)
    out = re.sub(r"_ASIM_LookupNetworkProtocol\s*\(\s*([\w.\[\]'\"]+)\s*\)", lambda m: PROTOCOL_INLINE.format(x=m.group(1)), out)
    # The disabled-parser guard reads a watchlist; on the lake the job itself decides what runs.
    out = re.sub(r"let\s+\w+\s*=\s*_ASIM_GetDisabledParsers\s*\([^;]*;\s*", "", out)
    out = re.sub(r"\|\s*where\s+not\s*\(\s*disabled\s*\)\s*", "", out)
    return out


def params_to_lets(params) -> str:
    """ParserParams list -> let statements with default values."""
    lets = []
    for p in params or []:
        name, typ, default = p.get("Name"), p.get("Type", "string"), p.get("Default")
        if name is None:
            continue
        if isinstance(default, bool):
            default = str(default).lower()
        if default is None:
            default = {"datetime": "datetime(null)", "dynamic": "dynamic([])", "bool": "false",
                       "int": "int(null)", "string": "'*'"}.get(typ, "''")
        lets.append(f"let {name} = {typ}({default});" if typ == "datetime" and not str(default).startswith("datetime")
                    else f"let {name} = {default};")
    return "\n".join(lets)


def load(path: str) -> tuple[str, list]:
    if path.endswith((".yaml", ".yml")):
        doc = yaml.safe_load(open(path, encoding="utf-8"))
        return doc.get("ParserQuery", ""), doc.get("ParserParams", [])
    return open(path, encoding="utf-8").read(), []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("parser")
    ap.add_argument("--out")
    a = ap.parse_args()
    query, params = load(a.parser)
    lake = params_to_lets(params) + "\n" + expand(query) if params else expand(query)
    remaining = sorted(set(FUNC_CALL.findall(lake)))
    if a.out:
        open(a.out, "w", encoding="utf-8").write(lake)
    print(f"parser: {a.parser}")
    print(f"parameters turned into lets: {[p.get('Name') for p in params or []]}")
    if remaining:
        print("NOT lake-safe yet. Function calls left:", ", ".join(remaining))
        print("Inline them by hand, or map this source through registry rules instead.")
        return 2
    print("lake-safe: no function calls left. Add a time filter and run it through the KQL checker.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
