"""Build the Sentinel data lake normalization infographics.

Writes one .dc.html artboard per infographic plus canvas.json for the Design
artifact, under ../canvas/project/. Run render.py afterwards for PNG and PDF.
"""
import json, os, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "canvas", "project")
os.makedirs(OUT, exist_ok=True)

W, H = 1080, 1350
NAVY, BLUE, SKY, PALE, LIME = "#05052F", "#001AFF", "#33A7FF", "#CBE9FF", "#CAFF00"
GREY, GREY2, MUTED = "#A5A5A5", "#DCDCDD", "#45455C"
FONT = "Arial, 'Liberation Sans', Helvetica, sans-serif"
TOTAL = 10
LEGAL = ("© 2026 LevelBlue Intellectual Property. LevelBlue logo, and registered trademarks and "
         "service marks are the property of LevelBlue Intellectual Property and/or LevelBlue "
         "affiliated companies. All other marks are the property of their respective owners.")

# ---------- small pieces ----------
SLASH = ('<svg width="40" height="28" viewBox="0 0 40 28" aria-hidden="true">'
         '<polygon points="8,0 14,0 6,28 0,28" fill="#00AAFF"></polygon>'
         '<polygon points="20,0 26,0 18,28 12,28" fill="#001AFF"></polygon>'
         '<polygon points="32,0 38,0 30,28 24,28" fill="#D5FE51"></polygon></svg>')


def down(color=BLUE):
    return ('<div style="display: flex; justify-content: center; height: 22px">'
            '<svg width="28" height="22" viewBox="0 0 28 22" aria-hidden="true">'
            f'<path d="M5 5 L14 16 L23 5" fill="none" stroke="{color}" stroke-width="3" '
            'stroke-linecap="round" stroke-linejoin="round"></path></svg></div>')


def right(color=BLUE):
    return ('<div style="display: flex; align-items: center; justify-content: center; width: 28px; flex: none">'
            '<svg width="22" height="28" viewBox="0 0 22 28" aria-hidden="true">'
            f'<path d="M5 5 L16 14 L5 23" fill="none" stroke="{color}" stroke-width="3" '
            'stroke-linecap="round" stroke-linejoin="round"></path></svg></div>')


def check(size=22, color=BLUE):
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" aria-hidden="true" style="flex: none">'
            f'<circle cx="12" cy="12" r="11" fill="{color}"></circle>'
            '<path d="M7 12.5 L10.5 16 L17 8.5" fill="none" stroke="#FFFFFF" stroke-width="2.6" '
            'stroke-linecap="round" stroke-linejoin="round"></path></svg>')


def cross(size=22, color=NAVY):
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" aria-hidden="true" style="flex: none">'
            f'<circle cx="12" cy="12" r="11" fill="#FFFFFF" stroke="{color}" stroke-width="2"></circle>'
            f'<path d="M8 8 L16 16 M16 8 L8 16" fill="none" stroke="{color}" stroke-width="2.6" '
            'stroke-linecap="round"></path></svg>')


def harvey(level, size=22):
    """level 0 empty, 1 quarter, 2 half, 3 three-quarter, 4 full."""
    c = f'<circle cx="12" cy="12" r="10" fill="#FFFFFF" stroke="{NAVY}" stroke-width="2"></circle>'
    seg = {
        0: "",
        1: f'<path d="M12 12 L12 2 A10 10 0 0 1 22 12 Z" fill="{BLUE}"></path>',
        2: f'<path d="M12 2 A10 10 0 0 1 12 22 Z" fill="{BLUE}"></path>',
        3: f'<path d="M12 12 L12 2 A10 10 0 1 1 2 12 Z" fill="{BLUE}"></path>',
        4: f'<circle cx="12" cy="12" r="10" fill="{BLUE}"></circle>',
    }[level]
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" role="img" '
            f'aria-label="{level} of 4" style="flex: none">{c}{seg}</svg>')


def icon(name, size=26, color=BLUE):
    paths = {
        "db": '<ellipse cx="12" cy="5" rx="8" ry="3"></ellipse><path d="M4 5 V19 C4 20.7 7.6 22 12 22 C16.4 22 20 20.7 20 19 V5"></path><path d="M4 12 C4 13.7 7.6 15 12 15 C16.4 15 20 13.7 20 12"></path>',
        "cols": '<rect x="3" y="4" width="18" height="16" rx="1"></rect><path d="M3 9 H21 M9 9 V20 M15 9 V20"></path>',
        "braces": '<path d="M9 4 C6 4 7 9 4 12 C7 15 6 20 9 20 M15 4 C18 4 17 9 20 12 C17 15 18 20 15 20"></path>',
        "text": '<path d="M4 6 H20 M4 10 H20 M4 14 H15 M4 18 H11"></path>',
        "list": '<path d="M8 6 H20 M8 12 H20 M8 18 H20"></path><circle cx="4" cy="6" r="1"></circle><circle cx="4" cy="12" r="1"></circle><circle cx="4" cy="18" r="1"></circle>',
        "tag": '<path d="M3 12 L12 3 H20 V11 L11 20 Z"></path><circle cx="16" cy="7" r="1.5"></circle>',
        "book": '<path d="M4 4 H10 C11 4 12 5 12 6 V20 C12 19 11 18 10 18 H4 Z M20 4 H14 C13 4 12 5 12 6 V20 C12 19 13 18 14 18 H20 Z"></path>',
        "stack": '<path d="M12 3 L21 8 L12 13 L3 8 Z M3 12 L12 17 L21 12 M3 16 L12 21 L21 16"></path>',
        "search": '<circle cx="10" cy="10" r="6"></circle><path d="M15 15 L21 21"></path>',
        "gauge": '<path d="M3 16 A9 9 0 0 1 21 16"></path><path d="M12 16 L16 9"></path>',
        "filter": '<path d="M3 4 H21 L14 12 V20 L10 18 V12 Z"></path>',
        "flask": '<path d="M9 3 H15 M10 3 V9 L4 19 C3.5 20 4 21 5 21 H19 C20 21 20.5 20 20 19 L14 9 V3"></path>',
        "bell": '<path d="M6 16 V11 A6 6 0 0 1 18 11 V16 L20 18 H4 Z M10 21 H14"></path>',
        "grid": '<rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect>',
        "doc": '<path d="M6 3 H14 L19 8 V21 H6 Z M14 3 V8 H19"></path>',
        "puzzle": '<path d="M4 8 H9 A2 2 0 1 1 13 8 H18 V13 A2 2 0 1 1 18 17 V20 H4 Z"></path>',
    }
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" aria-hidden="true" '
            f'style="flex: none; fill: none; stroke: {color}; stroke-width: 1.8; stroke-linecap: round; '
            f'stroke-linejoin: round">{paths[name]}</svg>')


def chip(text, bg=PALE, fg=NAVY, mono=False, border=None):
    fam = "Consolas, 'Liberation Mono', monospace" if mono else FONT
    size = "14px" if mono else "15px"
    b = f"border: 1px solid {border}; " if border else ""
    return (f'<span style="display: inline-flex; align-items: center; padding: 6px 10px; border-radius: 4px; white-space: nowrap; '
            f'{b}background: {bg}; color: {fg}; font-family: {fam}; font-size: {size}; line-height: 20px">{text}</span>')


def label(text, color=BLUE):
    return (f'<div style="font-size: 14px; letter-spacing: 1.5px; text-transform: uppercase; color: {color}">'
            f'{text}</div>')


def mono(t):
    return f'<span style="font-family: Consolas, \'Liberation Mono\', monospace">{t}</span>'


# ---------- page shell ----------
def page(n, title, subtitle, body, sources, doc_title):
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{doc_title}</title>
<script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
<style>
body{{margin:0}}
a{{color:#001AFF}}a:hover{{color:#05052F}}
</style>
</helmet>
<div style="width: {W}px; height: {H}px; box-sizing: border-box; display: flex; flex-direction: column; background: #FFFFFF; color: {NAVY}; font-family: {FONT}; overflow: hidden">
<div style="background: {NAVY}; padding: 40px 56px 36px; display: flex; flex-direction: column; gap: 14px; flex: none">
<div style="display: flex; align-items: center; gap: 14px">{SLASH}<span style="color: {PALE}; font-size: 14px; letter-spacing: 2px">SENTINEL DATA LAKE NORMALIZATION · {n} OF {TOTAL}</span></div>
<h1 style="margin: 0; color: #FFFFFF; font-size: 42px; line-height: 50px; font-weight: 400">{title}</h1>
<p style="margin: 0; color: {PALE}; font-size: 20px; line-height: 28px">{subtitle}</p>
<div style="width: 96px; height: 6px; background: {LIME}"></div>
</div>
<div style="flex: 1; min-height: 0; padding: 32px 56px 24px; display: flex; flex-direction: column; gap: 24px">
{body}
</div>
<div style="flex: none; padding: 14px 56px 18px; border-top: 1px solid {GREY2}; display: flex; flex-direction: column; gap: 6px; font-size: 12px; line-height: 16px; color: {MUTED}">
<div style="display: flex; justify-content: space-between; gap: 24px"><span>Sources: {sources}</span><span style="flex: none">Checked 16 October 2026</span></div>
<div>{LEGAL}</div>
</div>
</div>
</x-dc>
<script type="text/x-dc" data-dc-script data-props='{{"$preview":{{"width":{W},"height":{H}}}}}'>
class Component extends DCLogic {{
renderVals() {{
return {{}};
}}
}}
</script>
</body>
</html>
'''


CARD = f"background: #FFFFFF; border: 1px solid {GREY2}; border-radius: 6px"
TINT = f"background: #F2F8FF; border: 1px solid {PALE}; border-radius: 6px"

boards = []

# ============ 1. How ASIM works ============
def col(head, chips, note):
    items = "".join(f'<div>{c}</div>' for c in chips)
    return (f'<div style="flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 12px">'
            f'{label(head)}'
            f'<div style="{TINT}; padding: 16px; display: flex; flex-direction: column; gap: 10px; flex: 1">{items}</div>'
            f'<div style="font-size: 15px; line-height: 21px; color: {MUTED}; min-height: 63px">{note}</div></div>')

b1_cols = (
    col("Source tables", [chip("DeviceProcessEvents", "#FFFFFF", NAVY, True, GREY2),
                          chip("SecurityEvent 4688", "#FFFFFF", NAVY, True, GREY2),
                          chip("Sysmon event ID 1", "#FFFFFF", NAVY, True, GREY2),
                          chip("CrowdStrike Falcon", "#FFFFFF", NAVY, True, GREY2)],
        "Each product writes its own columns.")
    + right()
    + col("Source parsers", [chip("Defender XDR parser"), chip("Windows 4688 parser"),
                             chip("Sysmon parser"), chip("CrowdStrike parser")],
          "One per product, per schema. Reads exact column names.")
    + right()
    + col("Unifying parser", [chip("_Im_ProcessCreate", BLUE, "#FFFFFF", True),
                              f'<div style="font-size: 14px; line-height: 20px; color: {MUTED}; padding: 4px 2px 0">Takes filter parameters and passes them down to each source parser:</div>',
                              chip("starttime, endtime", "#FFFFFF", NAVY, True, GREY2),
                              chip("commandline_has_any", "#FFFFFF", NAVY, True, GREY2)],
          "Unions every source parser for the schema.")
    + right()
    + col("Content", [chip("Analytics rules"), chip("Hunting queries"), chip("Workbooks")],
          "Written once against the unifying parser.")
)

mapping_rows = [("InitiatingProcessFileName", "ActingProcessName"),
                ("ProcessCommandLine", "TargetProcessCommandLine"),
                ("AccountName", "ActorUsername"),
                ("DeviceName", "DvcHostname"),
                ("SHA256", "TargetProcessSHA256")]
map_html = "".join(
    f'<div style="display: grid; grid-template-columns: 1fr 40px 1fr; align-items: center; padding: 7px 0; border-bottom: 1px solid {GREY2}">'
    f'<span style="font-family: Consolas, \'Liberation Mono\', monospace; font-size: 16px">{a}</span>'
    f'<span style="color: {BLUE}; font-size: 18px; text-align: center">→</span>'
    f'<span style="font-family: Consolas, \'Liberation Mono\', monospace; font-size: 16px; color: {BLUE}">{b}</span></div>'
    for a, b in mapping_rows)

b1_body = f'''
<div style="display: flex; gap: 6px; align-items: stretch">{b1_cols}</div>
<div style="display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 28px">
<div style="background: {NAVY}; color: #FFFFFF; border-left: 0; border-radius: 6px; padding: 12px 16px; font-size: 16px; display: flex; gap: 10px; align-items: center"><span style="width: 14px; height: 14px; background: {LIME}; flex: none"></span>Depends on the product and the table schema</div>
<div style="background: {PALE}; color: {NAVY}; border-radius: 6px; padding: 12px 16px; font-size: 16px; display: flex; gap: 10px; align-items: center"><span style="width: 14px; height: 14px; background: {BLUE}; flex: none"></span>Same for every product</div>
</div>
<div style="{CARD}; padding: 20px 24px; display: flex; flex-direction: column; gap: 6px">
{label("What one source parser does: Defender XDR to the Process Event schema")}
<div style="display: grid; grid-template-columns: 1fr 40px 1fr; padding: 8px 0 2px; font-size: 13px; color: {MUTED}"><span>DeviceProcessEvents column</span><span></span><span>ASIM field</span></div>
{map_html}
<div style="font-size: 15px; line-height: 22px; color: {MUTED}; padding-top: 8px">It also sets {mono("EventType")} (for example ProcessCreated), {mono("EventVendor")}, {mono("EventProduct")} and {mono("EventSchemaVersion")}.</div>
</div>
<div style="display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px">
<div style="{CARD}; padding: 18px; display: flex; flex-direction: column; gap: 8px">{icon("puzzle")}<div style="font-size: 17px">No parser for a source</div><div style="font-size: 15px; line-height: 21px; color: {MUTED}">ASIM content returns nothing for that source.</div></div>
<div style="{CARD}; padding: 18px; display: flex; flex-direction: column; gap: 8px">{icon("cols")}<div style="font-size: 17px">Source schema changes</div><div style="font-size: 15px; line-height: 21px; color: {MUTED}">The parser usually returns no rows, with no error.</div></div>
<div style="{CARD}; padding: 18px; display: flex; flex-direction: column; gap: 8px">{icon("db")}<div style="font-size: 17px">Ingest-time option</div><div style="font-size: 15px; line-height: 21px; color: {MUTED}">A DCR transform writes native ASim tables such as {mono("ASimProcessEventLogs")}.</div></div>
</div>
'''
boards.append(("01-asim-model", "How ASIM works",
               "How ASIM normalizes data in Microsoft Sentinel",
               "The schemas are generic. The parsers are written for each product and each table.",
               b1_body, "Microsoft Learn, ASIM schemas and ASIM parsers overview"))

# ============ 2. Lake limit ============
def tier_step(text, state):
    if state == "ok":
        return (f'<div style="{CARD}; padding: 14px 16px; display: flex; gap: 12px; align-items: center; font-size: 17px">'
                f'{check()}<span>{text}</span></div>')
    if state == "no":
        return (f'<div style="background: #FFFFFF; border: 2px dashed {NAVY}; border-radius: 6px; padding: 13px 15px; display: flex; gap: 12px; align-items: center; font-size: 17px">'
                f'{cross()}<span>{text}</span></div>')
    return (f'<div style="background: #F4F4F5; border: 1px solid {GREY2}; border-radius: 6px; padding: 14px 16px; display: flex; gap: 12px; align-items: center; font-size: 17px; color: {MUTED}">'
            f'<span style="width: 22px; height: 22px; flex: none"></span><span>{text}</span></div>')

an = (tier_step("Hunting query or analytics rule", "ok") + down() +
      tier_step(f'Calls {mono("_Im_NetworkSession()")}', "ok") + down() +
      tier_step("Source parsers run (KQL functions)", "ok") + down() +
      tier_step("Tables return ASIM-shaped rows", "ok"))
lk = (tier_step("Hunting query or KQL job", "ok") + down(NAVY) +
      tier_step(f'Calls {mono("_Im_NetworkSession()")}', "no") + down(GREY) +
      tier_step("Source parsers never run", "grey") + down(GREY) +
      tier_step("No ASIM-shaped rows", "grey"))

b2_body = f'''
<div style="display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 28px">
<div style="display: flex; flex-direction: column; gap: 6px">{label("Analytics tier")}<div style="height: 6px"></div>{an}</div>
<div style="display: flex; flex-direction: column; gap: 6px">{label("Data lake tier", NAVY)}<div style="height: 6px"></div>{lk}</div>
</div>
<div style="background: {NAVY}; color: #FFFFFF; border-radius: 6px; padding: 22px 26px; display: flex; flex-direction: column; gap: 10px">
<div style="font-size: 22px; line-height: 30px">“Using out-of-the-box or custom functions isn't supported in KQL queries against the data lake.”</div>
<div style="font-size: 14px; color: {PALE}">Microsoft Learn, KQL queries in the Microsoft Sentinel data lake. Every ASIM parser is a function.</div>
</div>
<div style="display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 28px">
<div style="display: flex; flex-direction: column; gap: 12px">
{label("Also not supported in lake KQL", NAVY)}
<div style="display: flex; flex-wrap: wrap; gap: 8px">{chip("externaldata()", "#F4F4F5", NAVY, True)}{chip("adx()", "#F4F4F5", NAVY, True)}{chip("arg()", "#F4F4F5", NAVY, True)}{chip("ingestion_time()", "#F4F4F5", NAVY, True)}{chip("estimate_data_size()", "#F4F4F5", NAVY, True)}{chip("AzureDiagnostics and other legacy tables", "#F4F4F5", NAVY)}</div>
</div>
<div style="display: flex; flex-direction: column; gap: 12px">
{label("What still runs on the lake")}
<div style="display: flex; flex-direction: column; gap: 9px; font-size: 16px; line-height: 22px">
<div style="display: flex; gap: 10px">{check(20)}<span>KQL against the raw tables</span></div>
<div style="display: flex; gap: 10px">{check(20)}<span>Native ASim tables, already in ASIM shape</span></div>
<div style="display: flex; gap: 10px">{check(20)}<span>KQL jobs with parser logic pasted in as plain KQL</span></div>
<div style="display: flex; gap: 10px">{check(20)}<span>Spark notebooks</span></div>
</div>
</div>
</div>
<div style="display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px">
<div style="{TINT}; padding: 14px 16px"><div style="font-size: 26px; color: {BLUE}">15 min</div><div style="font-size: 14px; color: {MUTED}; line-height: 20px">before ingested data can be queried</div></div>
<div style="{TINT}; padding: 14px 16px"><div style="font-size: 26px; color: {BLUE}">500,000 rows</div><div style="font-size: 14px; color: {MUTED}; line-height: 20px">or 64 MB per interactive result</div></div>
<div style="{TINT}; padding: 14px 16px"><div style="font-size: 26px; color: {BLUE}">30 / min, 10 at once</div><div style="font-size: 14px; color: {MUTED}; line-height: 20px">query limits per tenant</div></div>
</div>
<div style="{CARD}; padding: 16px 20px; display: grid; grid-template-columns: 250px minmax(0, 1fr); gap: 20px; align-items: start">
<div style="display: flex; flex-direction: column; gap: 6px">{label("Same hunt, rewritten for the lake")}<div style="font-size: 15px; line-height: 21px; color: {MUTED}">The parser's mapping travels inside the query as plain KQL.</div></div>
<div style="background: {NAVY}; border-radius: 4px; padding: 12px 16px; font-family: Consolas, 'Liberation Mono', monospace; font-size: 14px; line-height: 21px; color: #FFFFFF; white-space: pre">CommonSecurityLog
| where DeviceVendor == "Palo Alto Networks"
| project-rename SrcIpAddr = SourceIP,
    DstIpAddr = DestinationIP, DvcHostname = DeviceName
| extend EventVendor = "Palo Alto Networks"</div>
</div>
'''
boards.append(("02-lake-limit", "Why ASIM stops at the lake",
               "ASIM parsers do not run on the Sentinel data lake",
               "Lake KQL does not support functions, and every ASIM parser is a function.",
               b2_body, "Microsoft Learn, KQL queries in the data lake; Troubleshoot KQL queries for the data lake"))

# ============ 3. Coverage ============
import math
pts = []
for i in range(0, 101):
    x = 40 + i * 9.08
    y = 400 - 360 * math.exp(-i / 11.0)
    pts.append((x, y))
line = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in pts)
head_pts = [p for p in pts if p[0] <= 40 + 18 * 9.08]
head = ("M 40 400 L " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in head_pts)
        + f" L {head_pts[-1][0]:.1f} 400 Z")
tail_pts = [p for p in pts if p[0] >= head_pts[-1][0]]
tail = (f"M {tail_pts[0][0]:.1f} 400 L " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in tail_pts)
        + f" L {tail_pts[-1][0]:.1f} 400 Z")
hx = head_pts[-1][0]

curve_svg = (f'<svg width="968" height="420" viewBox="0 0 968 420" aria-hidden="true" style="position: absolute; left: 0; top: 0">'
             f'<path d="{tail}" fill="#EEEEF0"></path>'
             f'<path d="{head}" fill="{BLUE}"></path>'
             f'<path d="{line}" fill="none" stroke="{NAVY}" stroke-width="2"></path>'
             f'<path d="M 40 20 L 40 400 L 950 400" fill="none" stroke="{NAVY}" stroke-width="1.5"></path>'
             f'<path d="M {hx:.1f} 40 L {hx:.1f} 400" fill="none" stroke="{NAVY}" stroke-width="1.5" stroke-dasharray="5 5"></path>'
             '</svg>')

def src_row(ic, head_t, body_t):
    return (f'<div style="display: flex; gap: 16px; align-items: flex-start; padding: 14px 0; border-bottom: 1px solid {GREY2}">'
            f'{icon(ic, 28)}<div style="display: flex; flex-direction: column; gap: 4px"><div style="font-size: 18px">{head_t}</div>'
            f'<div style="font-size: 15px; line-height: 21px; color: {MUTED}">{body_t}</div></div></div>')

b3_body = f'''
<div style="position: relative; width: 968px; height: 440px; flex: none">
{curve_svg}
<div style="position: absolute; left: 54px; top: 318px; width: 120px; color: #FFFFFF; font-size: 16px; line-height: 21px">ASIM parser exists</div>
<div style="position: absolute; left: {int(hx) + 40}px; top: 200px; width: 360px; font-size: 18px; line-height: 24px">Long tail with no parser</div>
<div style="position: absolute; left: {int(hx) + 40}px; top: 228px; width: 520px; font-size: 15px; line-height: 21px; color: {MUTED}">Niche SaaS apps, in-house applications, custom _CL tables, vendor solutions that ship only their own rules</div>
<div style="position: absolute; left: 40px; top: 410px; width: 520px; font-size: 13px; color: {MUTED}">Data sources, ranked by ingest volume</div>
<div style="position: absolute; left: 600px; top: 410px; width: 350px; font-size: 13px; color: {MUTED}; text-align: right">Shape is illustrative, not measured</div>
</div>
<div style="display: flex; flex-direction: column">
{src_row("grid", "A parser exists", "Every ASIM analytics rule, hunting query and workbook covers the source with no extra work.")}
{src_row("puzzle", "No parser exists", "ASIM content returns nothing for the source. Someone has to write and maintain a parser: Microsoft, the vendor, the community or you.")}
{src_row("doc", "The vendor solution ships only its own rules", "Those rules query the raw table directly. They do not feed or use ASIM content.")}
</div>
<div style="display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 28px">
<div style="display: flex; flex-direction: column; gap: 12px">{label("Usually covered by ASIM parsers")}
<div style="display: flex; flex-wrap: wrap; gap: 8px">{chip("Major firewalls")}{chip("Web proxies")}{chip("DNS servers")}{chip("EDR platforms")}{chip("Linux sshd and su/sudo")}{chip("Cloud audit logs")}</div></div>
<div style="display: flex; flex-direction: column; gap: 12px">{label("Usually not covered", NAVY)}
<div style="display: flex; flex-wrap: wrap; gap: 8px">{chip("Niche SaaS apps", "#F4F4F5")}{chip("In-house applications", "#F4F4F5")}{chip("Custom _CL tables", "#F4F4F5")}{chip("OT and IoT gateways", "#F4F4F5")}{chip("Vendor solutions without parsers", "#F4F4F5")}</div></div>
</div>
'''
boards.append(("03-asim-coverage", "ASIM coverage at scale",
               "ASIM coverage depends on which parsers exist",
               "The schemas are product-neutral, but a source only gets ASIM content once someone writes its parser.",
               b3_body, "Microsoft Learn, ASIM parsers overview; Microsoft Tech Community, ASIM additions (June 2026)"))

# ============ 4. Methods compared ============
methods = [
    ("Per-source DCR into ASim or custom tables", "Ingest time", 4, "Full ASIM fields", 4, "One DCR per source", "Yes, check table tier support", "Top 10 to 20 sources by volume"),
    ("ASIM parsers at query time", "Query time", 4, "Full ASIM fields", 1, "Microsoft maintains", "No", "Analytics-tier tables only"),
    ("ASIM parser logic inlined in KQL jobs or notebooks", "Query time", 4, "Full ASIM, where a parser exists", 1, "Scheduled sync from the Azure-Sentinel GitHub repo", "Yes", "Sources Microsoft already parses"),
    ("Discovery scan and entity index", "Scheduled job", 2, "IP, user, host, hash, URL", 1, "One synonym dictionary", "Yes", "The long tail of tables"),
    ("Syslog template mining", "Scheduled job", 3, "Fields per message template", 2, "Review new templates", "Yes", "Unix syslog, auditd, raw text"),
    ("Free-text search", "Query time", 1, "Literal indicator matches", 0, "None", "Yes, slow; test union * first", "Backstop for indicators"),
]
grid_cols = "grid-template-columns: 230px 190px 190px 130px minmax(0, 1fr)"
hdr = (f'<div style="display: grid; {grid_cols}; gap: 16px; padding: 0 16px 10px; font-size: 13px; letter-spacing: 1px; text-transform: uppercase; color: {BLUE}">'
       '<span>Method</span><span>Fields you get</span><span>Upkeep at hundreds of sources</span><span>Runs on the lake</span><span>Use it for</span></div>')
rows = ""
for i, (m, when, fd, ft, eff, et, lake, use) in enumerate(methods):
    bg = "#F2F8FF" if i % 2 == 0 else "#FFFFFF"
    lake_ic = cross(20) if lake == "No" else check(20)
    rows += (f'<div style="display: grid; {grid_cols}; gap: 16px; padding: 14px 16px; background: {bg}; border-bottom: 1px solid {GREY2}; align-items: start">'
             f'<div style="display: flex; flex-direction: column; gap: 4px"><span style="font-size: 17px; line-height: 22px">{m}</span><span style="font-size: 13px; color: {MUTED}">{when}</span></div>'
             f'<div style="display: flex; gap: 10px; align-items: flex-start">{harvey(fd)}<span style="font-size: 15px; line-height: 21px">{ft}</span></div>'
             f'<div style="display: flex; gap: 10px; align-items: flex-start">{harvey(eff)}<span style="font-size: 15px; line-height: 21px">{et}</span></div>'
             f'<div style="display: flex; gap: 8px; align-items: flex-start">{lake_ic}<span style="font-size: 15px; line-height: 21px">{lake}</span></div>'
             f'<div style="font-size: 15px; line-height: 21px">{use}</div></div>')
legend = (f'<div style="display: flex; gap: 28px; align-items: center; font-size: 14px; color: {MUTED}; flex-wrap: wrap">'
          f'<span style="display: flex; gap: 8px; align-items: center">{harvey(4, 18)}{harvey(2, 18)}{harvey(0, 18)} Fields: full to none</span>'
          f'<span style="display: flex; gap: 8px; align-items: center">{harvey(4, 18)}{harvey(1, 18)}{harvey(0, 18)} Upkeep: heavy to none</span></div>')
def route(src_t, meth_t, tier_t):
    return (f'<div style="display: grid; grid-template-columns: minmax(0, 1fr) 28px minmax(0, 1fr) 110px; gap: 10px; align-items: center">'
            f'<div style="{CARD}; padding: 10px 14px; font-size: 16px">{src_t}</div>{right()}'
            f'<div style="background: {PALE}; border-radius: 6px; padding: 10px 14px; font-size: 16px">{meth_t}</div>'
            f'<div style="font-size: 14px; color: {MUTED}">{tier_t}</div></div>')

b4_routes = (route("Source has an ASIM parser", "Inline the ASIM parser logic", "Tier 1")
             + route("Structured fields, no parser", "Discovery scan and entity index", "Tier 2")
             + route("Raw text: syslog, auditd", "Template mining, then value regex", "Tier 2")
             + route("Any source, any time", "Free-text search as a backstop", "Tier 3"))

b4_body = f'''
{legend}
<div style="display: flex; flex-direction: column">{hdr}{rows}</div>
<div style="display: flex; flex-direction: column; gap: 8px">{label("Route each source to a method")}{b4_routes}</div>
<div style="background: {NAVY}; color: #FFFFFF; border-radius: 6px; padding: 22px 26px; display: flex; gap: 20px; align-items: center">
<div style="width: 8px; align-self: stretch; background: {LIME}; flex: none"></div>
<div style="display: flex; flex-direction: column; gap: 8px"><div style="font-size: 21px; line-height: 28px">Mix for hundreds of sources: inlined ASIM logic, the entity index, template mining and free-text search.</div>
<div style="font-size: 15px; line-height: 21px; color: {PALE}">Keep per-source DCRs for the few highest-volume sources. Writing and maintaining hundreds of them does not scale.</div></div>
</div>
'''
boards.append(("04-methods-compared", "Normalization methods compared",
               "Six ways to get common fields, compared at scale",
               "What each method gives you, what it costs to maintain, and whether it runs on the lake.",
               b4_body, "Microsoft Learn, ASIM and data lake KQL documentation; LevelBlue analysis"))

# ============ 5. Discovery pipeline ============
def stage(ic, head_t, body_t, extra=""):
    return (f'<div style="{CARD}; padding: 14px 18px; display: flex; gap: 16px; align-items: flex-start">{icon(ic, 28)}'
            f'<div style="display: flex; flex-direction: column; gap: 6px; flex: 1; min-width: 0"><div style="font-size: 18px">{head_t}</div>'
            f'<div style="font-size: 15px; line-height: 21px; color: {MUTED}">{body_t}</div>{extra}</div></div>')

def reader(ic, head_t, how, ex):
    return (f'<div style="{TINT}; padding: 14px 16px; display: flex; flex-direction: column; gap: 6px">'
            f'<div style="display: flex; gap: 10px; align-items: center">{icon(ic, 24)}<span style="font-size: 17px">{head_t}</span></div>'
            f'<div style="font-size: 14px; line-height: 20px">{how}</div>'
            f'<div style="font-size: 13px; line-height: 18px; color: {MUTED}">{ex}</div></div>')

inv_rows = [("CommonSecurityLog", "SourceIP", "string", "0.98", "203.0.113.17"),
            ("AppAudit_CL", "Properties.client.addr", "dynamic", "0.71", "198.51.100.4"),
            ("Syslog", "sshd: from &lt;*&gt; port", "template", "0.64", "192.0.2.9")]
inv = (f'<div style="display: grid; grid-template-columns: 170px 220px 90px 70px minmax(0, 1fr); gap: 10px; font-size: 12px; color: {BLUE}; text-transform: uppercase; letter-spacing: 1px; padding-top: 4px">'
       '<span>Table</span><span>Field path</span><span>Type</span><span>Fill</span><span>Sample</span></div>')
for r in inv_rows:
    inv += (f'<div style="display: grid; grid-template-columns: 170px 220px 90px 70px minmax(0, 1fr); gap: 10px; font-family: Consolas, \'Liberation Mono\', monospace; font-size: 13px; color: {NAVY}; border-top: 1px solid {GREY2}; padding-top: 4px">'
            + "".join(f"<span>{c}</span>" for c in r) + "</div>")

b5_body = f'''
<div style="display: flex; flex-direction: column; gap: 4px">
{stage("db", "Every table in the lake", "Microsoft tables, CommonSecurityLog, Syslog, custom _CL tables. A Spark notebook lists and samples them without the interactive row cap.")}
{down()}
<div style="display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px">
{reader("cols", "Typed columns", f'Read the table schema ({mono("getschema")}, {mono("df.schema")})', "SigninLogs.UserPrincipalName")}
{reader("braces", "JSON and dynamic columns", f'Pull keys from sampled rows ({mono("bag_keys")})', "AdditionalFields, RawEventData, Properties")}
{reader("text", "Key=value and raw text", f'{mono("parse_kv")}, regex, template mining', "AdditionalExtensions, SyslogMessage, RawData")}
</div>
{down()}
{stage("list", "Field inventory", "One row per table and field path, with type, fill rate and a sample value. Example rows:", f'<div style="display: flex; flex-direction: column; gap: 4px; padding-top: 4px">{inv}</div>')}
{down()}
{stage("filter", "Classify by value, not only by name", "Catches badly named columns such as cs4 or field7 that hold IP addresses.", f'<div style="display: flex; flex-wrap: wrap; gap: 8px; padding-top: 4px">{chip("IPv4 / IPv6")}{chip("UPN or email")}{chip("SHA256 / MD5")}{chip("URL")}{chip("Hostname / FQDN")}</div>')}
{down()}
<div style="display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px">
{stage("book", "Synonym dictionary", "Column-name patterns mapped to ASIM field names. One file.")}
{stage("tag", "Template registry", "Syslog message templates with each slot mapped to an ASIM field.")}
</div>
{down()}
<div style="background: {NAVY}; border-radius: 6px; padding: 16px 20px; display: flex; flex-direction: column; gap: 10px">
<div style="display: flex; justify-content: space-between; align-items: center; gap: 16px"><span style="color: #FFFFFF; font-size: 18px">Entity index: one narrow table with ASIM column names</span><span style="color: {LIME}; font-size: 14px; flex: none">Re-run monthly, review the diff</span></div>
<div style="display: flex; flex-wrap: wrap; gap: 6px">{"".join(chip(c, "#1B1B4A", "#FFFFFF", True) for c in ["SourceTable", "SrcIpAddr", "DstIpAddr", "ActorUsername", "DvcHostname", "Url", "FileHash", "Domain"])}</div>
</div>
</div>
'''
boards.append(("05-discovery-pipeline", "Discovery pipeline",
               "Find the common fields, then index them",
               "Read three kinds of field, classify the values, and write one entity index for hunting.",
               b5_body, "Microsoft Learn, data lake KQL and notebooks; LevelBlue design"))

# ============ 6. Confidence matrix ============
src_cols = ["ASIM-parsed or Microsoft", "CEF standard columns", "CEF cs1 to cs6", "Custom JSON _CL", "Syslog, mapped templates", "Syslog, long tail"]
ent_rows = [("IP address", "HHMHHM"), ("File hash", "HHMHHM"), ("URL or domain", "HHMMML"),
            ("Hostname", "HMLMML"), ("Username", "HMLMML"), ("Role: source or target", "HMLLML"),
            ("Event type and result", "HLLLML")]
lvl = {"H": (BLUE, "#FFFFFF", "High"), "M": ("#8CCBFF", NAVY, "Medium"), "L": ("#F1F1F3", NAVY, "Low")}
mx = (f'<div style="display: grid; grid-template-columns: 190px repeat(6, minmax(0, 1fr)); gap: 4px">'
      f'<span></span>' + "".join(f'<span style="font-size: 13px; line-height: 17px; color: {MUTED}; padding: 0 4px 6px; align-self: end">{c}</span>' for c in src_cols))
for name, levels in ent_rows:
    mx += f'<span style="font-size: 16px; line-height: 20px; align-self: center">{name}</span>'
    for ch in levels:
        bg, fg, t = lvl[ch]
        border = f"border: 1px dashed {GREY}; " if ch == "L" else ""
        mx += (f'<span style="{border}background: {bg}; color: {fg}; height: 52px; box-sizing: border-box; border-radius: 4px; '
               f'display: flex; align-items: center; justify-content: center; font-size: 15px">{t}</span>')
mx += "</div>"

def norm_row(raws, out):
    rs = "".join(f'<div>{chip(r, "#F4F4F5", NAVY, True)}</div>' for r in raws)
    return (f'<div style="display: flex; align-items: center; gap: 14px"><div style="display: flex; flex-direction: column; gap: 6px; width: 330px">{rs}</div>'
            f'{right()}<div>{chip(out, BLUE, "#FFFFFF", True)}</div></div>')

b6_body = f'''
{mx}
<div style="font-size: 14px; line-height: 20px; color: {MUTED}">Expected confidence, based on how each field is found. Measure it per source with the coverage report before quoting it to anyone.</div>
<div style="display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr); gap: 28px">
<div style="{CARD}; padding: 18px 20px; display: flex; flex-direction: column; gap: 14px">
{label("Normalize values, not only field names")}
{norm_row(["CONTOSO\\jsmith", "jsmith@contoso.com", "S-1-5-21-…-1104"], "jsmith")}
{norm_row(["WS-0412.corp.contoso.com", "ws-0412"], "ws-0412")}
<div style="display: flex; flex-wrap: wrap; gap: 6px; padding-top: 4px">{chip("Lowercase", "#F2F8FF")}{chip("Split domain and user", "#F2F8FF")}{chip("Resolve SIDs", "#F2F8FF")}{chip("Keep FQDN and short name", "#F2F8FF")}</div>
</div>
<div style="display: flex; flex-direction: column; gap: 12px">
{label("What you can say with confidence", NAVY)}
<div style="display: flex; gap: 10px; font-size: 16px; line-height: 22px">{check(20)}<span>This IP, hash or domain appeared, or did not appear, in these sources.</span></div>
<div style="display: flex; gap: 10px; font-size: 16px; line-height: 22px">{cross(20)}<span>This user logged on and it succeeded, outside parsed sources.</span></div>
<div style="display: flex; gap: 10px; font-size: 16px; line-height: 22px">{cross(20)}<span>Lateral movement across every source.</span></div>
</div>
</div>
'''
boards.append(("06-confidence-matrix", "Confidence by entity and source",
               "How far common fields can be trusted",
               "Indicators hold up almost everywhere. Roles and outcomes need a parser or template.",
               b6_body, "LevelBlue analysis of field extraction methods"))

# ============ 7. Coverage tiers and drift ============
def tier(n, name, depth_pct, desc, chips_):
    cs = "".join(chip(c) for c in chips_)
    return (f'<div style="{CARD}; padding: 16px 20px; display: grid; grid-template-columns: 220px minmax(0, 1fr); gap: 20px; align-items: center">'
            f'<div style="display: flex; flex-direction: column; gap: 4px"><span style="font-size: 13px; color: {BLUE}; letter-spacing: 1px">TIER {n}</span><span style="font-size: 20px">{name}</span></div>'
            f'<div style="display: flex; flex-direction: column; gap: 8px">'
            f'<div style="height: 12px; background: #F1F1F3; border-radius: 6px"><div style="width: {depth_pct}%; height: 12px; background: {BLUE}; border-radius: 6px"></div></div>'
            f'<div style="font-size: 15px; line-height: 21px; color: {MUTED}">{desc}</div>'
            f'<div style="display: flex; flex-wrap: wrap; gap: 6px">{cs}</div></div></div>')

def chk(ic, t, d):
    return (f'<div style="{TINT}; padding: 14px 16px; display: flex; flex-direction: column; gap: 6px">{icon(ic, 24)}'
            f'<div style="font-size: 16px">{t}</div><div style="font-size: 14px; line-height: 19px; color: {MUTED}">{d}</div></div>')

spark = [92, 93, 91, 92, 94, 92, 93, 41, 40, 42, 41, 40]
sx = lambda i: 30 + i * 42
sy = lambda v: 150 - v * 1.3
sp = "M " + " L ".join(f"{sx(i)} {sy(v):.1f}" for i, v in enumerate(spark))
drift_svg = (f'<svg width="520" height="170" viewBox="0 0 520 170" aria-hidden="true" style="position: absolute; left: 0; top: 0">'
             f'<path d="M 30 10 L 30 150 L 500 150" fill="none" stroke="{NAVY}" stroke-width="1.5"></path>'
             f'<path d="M 30 {sy(80):.1f} L 500 {sy(80):.1f}" fill="none" stroke="{GREY}" stroke-width="1.5" stroke-dasharray="5 5"></path>'
             f'<path d="{sp}" fill="none" stroke="{BLUE}" stroke-width="3" stroke-linejoin="round"></path>'
             f'<circle cx="{sx(7)}" cy="{sy(41):.1f}" r="8" fill="{LIME}" stroke="{NAVY}" stroke-width="2"></circle>'
             '</svg>')

b7_body = f'''
<div style="display: flex; flex-direction: column; gap: 10px">
{tier(1, "ASIM-parsed", 100, "Full schema: roles, event type and result.", ["SrcIpAddr vs DstIpAddr", "ActorUsername vs TargetUsername", "EventType", "EventResult"])}
{tier(2, "Entity only", 55, "Entities without roles or outcome.", ["IP", "User", "Host", "Hash", "URL"])}
{tier(3, "Search only", 20, "A literal string match, nothing more.", [f'{mono("where * has")}'])}
</div>
<div style="display: flex; flex-direction: column; gap: 12px">
{label("Checks on every run")}
<div style="display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px">
{chk("gauge", "Extraction rate", "Share of rows per table with at least one entity")}
{chk("grid", "Fill rate per entity", "How often each ASIM column is populated")}
{chk("cols", "Unmapped columns", "High-fill columns the dictionary does not cover")}
{chk("tag", "Template match rate", "Share of syslog lines matching a known template")}
{chk("search", "Hand-checked sample", "50 to 100 rows per source, reviewed by an analyst")}
{chk("flask", "Canary events", "Known logon, IP and hash generated on purpose")}
</div>
</div>
<div style="{CARD}; padding: 18px 20px; display: grid; grid-template-columns: 520px minmax(0, 1fr); gap: 24px; align-items: center">
<div style="position: relative; width: 520px; height: 190px">
{drift_svg}
<div style="position: absolute; left: 30px; top: 160px; width: 300px; font-size: 13px; color: {MUTED}">Weeks</div>
<div style="position: absolute; left: 345px; top: 70px; width: 160px; font-size: 13px; color: {MUTED}">Alert threshold</div>
<div style="position: absolute; left: 340px; top: 112px; width: 170px; font-size: 13px; color: {NAVY}">Vendor update lands</div>
</div>
<div style="display: flex; flex-direction: column; gap: 10px">
<div style="display: flex; gap: 10px; align-items: center">{icon("bell", 26)}<span style="font-size: 19px">Drift alert</span></div>
<div style="font-size: 15px; line-height: 21px; color: {MUTED}">A parser or mapping that stops matching returns fewer rows, not an error. A drop in extraction rate is usually the first sign that a vendor changed a format.</div>
<div style="font-size: 13px; color: {MUTED}">Chart is illustrative.</div>
</div>
</div>
'''
boards.append(("07-coverage-tiers", "Coverage tiers and drift",
               "Measure coverage for each source",
               "Tier every source by how deep a query can see, then watch for formats that change underneath you.",
               b7_body, "LevelBlue design for coverage reporting"))

# ============ 8. The ask ============
def numbered(i, t, d):
    return (f'<div style="display: flex; gap: 14px; align-items: flex-start; padding: 12px 0; border-bottom: 1px solid {GREY2}">'
            f'<span style="width: 34px; height: 34px; border-radius: 17px; background: {BLUE}; color: #FFFFFF; display: flex; align-items: center; justify-content: center; font-size: 17px; flex: none">{i}</span>'
            f'<div style="display: flex; flex-direction: column; gap: 4px"><span style="font-size: 18px; line-height: 24px">{t}</span>'
            f'<span style="font-size: 15px; line-height: 21px; color: {MUTED}">{d}</span></div></div>')

def today(t):
    return (f'<div style="display: flex; gap: 10px; align-items: flex-start; font-size: 16px; line-height: 22px; color: #FFFFFF">'
            f'<span style="width: 10px; height: 10px; background: {LIME}; margin-top: 6px; flex: none"></span><span>{t}</span></div>')

def work(t, effect, req, strong):
    bg, fg = (BLUE, "#FFFFFF") if strong == 2 else ((PALE, NAVY) if strong == 1 else ("#F1F1F3", NAVY))
    return (f'<div style="display: grid; grid-template-columns: minmax(0, 1fr) 150px 120px; gap: 16px; align-items: center; padding: 10px 0; border-bottom: 1px solid #23235A">'
            f'<span style="font-size: 16px; line-height: 22px; color: #FFFFFF">{t}</span>'
            f'<span style="background: {bg}; color: {fg}; border-radius: 4px; padding: 6px 10px; font-size: 15px; text-align: center">{effect}</span>'
            f'<span style="font-size: 14px; color: {PALE}">{req}</span></div>')

b8_body = f'''
<div style="display: flex; flex-direction: column">
{label("Requested from the Sentinel product group")}
{numbered(1, "Run ASIM parsers in lake KQL and KQL jobs", "Unifying and source-specific parsers, or a lake-specific build of them.")}
{numbered(2, "Document query-scoped functions in lake KQL", "State whether let-defined functions are supported, so inlined parsers can stay readable.")}
{numbered(3, "Lake tier for every native ASim table", "So ingest-time normalization can land straight in the lake.")}
{numbered(4, "ASIM output from filter-and-split transforms", "Map fields to ASIM columns while routing data to the lake tier.")}
{numbered(5, "A recommended normalization pattern for the lake", "Published guidance for hunting across hundreds of third-party sources.")}
</div>
<div style="background: {NAVY}; border-radius: 6px; padding: 18px 24px; display: flex; flex-direction: column">
<div style="display: grid; grid-template-columns: minmax(0, 1fr) 150px 120px; gap: 16px; font-size: 13px; letter-spacing: 1.5px; color: {LIME}; padding-bottom: 6px"><span>CUSTOM WORK TODAY</span><span style="text-align: center">WITH THE REQUESTS</span><span>REQUEST</span></div>
{work("Copy ASIM parser logic into every lake query and KQL job", "Removed", "1, 2", 2)}
{work("Sync parser YAML from the Azure-Sentinel GitHub repo", "Removed", "1", 2)}
{work("Per-source DCRs for the highest-volume sources", "Reduced", "3, 4", 1)}
{work("Entity index for sources with no parser", "Still needed", "", 0)}
{work("Syslog template mining", "Still needed", "", 0)}
{work("Coverage and drift checks per source", "Still needed", "", 0)}
</div>
<div style="{TINT}; padding: 18px 22px; display: flex; gap: 16px; align-items: center">
{icon("doc", 28)}
<div style="font-size: 16px; line-height: 23px">Status on 16 October 2026: Sentinel's What's new page, from July 2025 to September 2026, lists no item for ASIM in the data lake or for function support in lake KQL. ASIM parser work continues on the analytics tier.</div>
</div>
'''
boards.append(("08-ask-to-microsoft", "The ask to Microsoft",
               "What ASIM support in the data lake would change",
               "Native support would replace custom work that every team hunting across third-party sources repeats today.",
               b8_body, "Microsoft Learn, What's new in Microsoft Sentinel; data lake KQL documentation"))

# ============ 9. Worked example: Linux syslog ============
import html as _html

def code(t, size=13):
    return (f'<div style="background: {NAVY}; border-radius: 4px; padding: 12px 14px; font-family: Consolas, \'Liberation Mono\', monospace; '
            f'font-size: {size}px; line-height: 19px; color: #FFFFFF; white-space: pre">{_html.escape(t.strip(chr(10)), quote=False)}</div>')

def step(n, head_t, body, note):
    return (f'<div style="display: flex; flex-direction: column; gap: 8px; min-width: 0">'
            f'<div style="display: flex; gap: 10px; align-items: center"><span style="width: 28px; height: 28px; border-radius: 14px; background: {BLUE}; color: #FFFFFF; display: flex; align-items: center; justify-content: center; font-size: 15px; flex: none">{n}</span>'
            f'<span style="font-size: 18px">{head_t}</span></div>{body}'
            f'<div style="font-size: 14px; line-height: 19px; color: {MUTED}">{note}</div></div>')

def hl(t, bg, fg=NAVY):
    return f'<span style="background: {bg}; color: {fg}; padding: 1px 3px; border-radius: 3px">{t}</span>'

MONO = "font-family: Consolas, 'Liberation Mono', monospace"
raw_lines = (
    f'<div>web-07 sshd[2214]: Failed password for invalid user {hl("admin", PALE)} from {hl("203.0.113.45", LIME)} port 52114 ssh2</div>'
    f'<div style="color: {MUTED}">web-07 sshd[2214]: Accepted publickey for deploy from 198.51.100.20 port 40022 ssh2</div>'
    f'<div style="color: {MUTED}">web-07 sudo: deploy : TTY=pts/0 ; PWD=/home/deploy ; USER=root ; COMMAND=/usr/bin/systemctl restart nginx</div>')
out_chips = "".join(chip(c, bg, NAVY, True) for c, bg in [
    ("TargetUsername = admin", PALE), ("SrcIpAddr = 203.0.113.45", LIME),
    ("EventType = Logon", "#F2F8FF"), ("EventResult = Failure", "#F2F8FF"), ("DvcHostname = web-07", "#F2F8FF")])

q1 = r'''
Syslog
| where TimeGenerated > ago(7d)
| where ProcessName == "sshd"
| reduce by SyslogMessage
    with threshold = 0.1
| top 20 by Count
'''
q2 = r'''
- process: sshd
  match: "Failed password for"
  fields:
    TargetUsername: 'for (?:invalid user )?(\S+) from'
    SrcIpAddr: 'from (\S+) port'
  EventType: Logon
  EventResult: Failure
'''
q3 = r'''
Syslog
| where TimeGenerated > ago(1h)
| where ProcessName == "sshd" and SyslogMessage has "Failed password for"
| extend TargetUsername = extract(@"for (?:invalid user )?(\S+) from", 1, SyslogMessage),
         SrcIpAddr = extract(@"from (\S+) port", 1, SyslogMessage)
| project TimeGenerated, SourceTable = "Syslog", EventVendor = "OpenSSH",
          EventType = "Logon", EventResult = "Failure", SrcIpAddr,
          TargetUsername, DvcHostname = Computer
'''
q4 = r'''
Syslog
| where TimeGenerated > ago(1h)
| where not(SyslogMessage has_any
    ("Failed password for", "Accepted"))
| extend Ip = extract_all(
    @"\b(\d{1,3}(?:\.\d{1,3}){3})\b", SyslogMessage)
| mv-expand SrcIpAddr = Ip to typeof(string)
'''
q5 = r'''
HuntIndex_KQL_CL
| where SrcIpAddr == "203.0.113.45"
| summarize Events = count(),
    Sources = make_set(SourceTable)
    by EventType, EventResult
'''

b9_body = f'''
<div style="{CARD}; padding: 16px 20px; display: flex; flex-direction: column; gap: 12px">
<div style="display: flex; justify-content: space-between; gap: 16px">{label("Raw lines as they land: ProcessName and SyslogMessage only")}<span style="font-size: 13px; color: {MUTED}">Collector adds no parsing</span></div>
<div style="{MONO}; font-size: 13px; line-height: 22px; display: flex; flex-direction: column; gap: 2px; white-space: nowrap">{raw_lines}</div>
<div style="display: flex; gap: 10px; align-items: center">{right()}<div style="display: flex; flex-wrap: wrap; gap: 6px">{out_chips}</div></div>
</div>
<div style="display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 24px">
{step(1, "Find the templates", code(q1), "Run per program. Test reduce on your lake; Drain3 in a notebook also works.")}
{step(2, "Record each template once", code(q2), "One registry entry per template, kept in Git with the generator.")}
</div>
{step(3, "Generator writes plain KQL for each template", code(q3, 12.5), "One block per template, unioned into one KQL job. No functions, so it runs in lake KQL. Output columns use ASIM names.")}
<div style="display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 24px">
{step(4, "Catch every unmatched line", code(q4), "Unmatched lines still give up their IPs, as Tier 2 rows.")}
{step(5, "Hunt the index, not the raw table", code(q5), "The KQL job writes HuntIndex_KQL_CL on a schedule. Analysts and the data lake MCP query this one table.")}
</div>
'''
boards.append(("09-syslog-worked-example", "Worked example: syslog",
               "Worked example: Linux syslog into the entity index",
               "No parsing at the collector. Every step below is plain KQL that runs in the lake.",
               b9_body, "Microsoft Learn, KQL reduce, extract, extract_all and data lake KQL jobs; LevelBlue design"))

# ============ 10. Scaling over many raw sources ============
def funnel(t, pct, bg, fg, note=""):
    n = ""
    return (f'<div style="display: flex; align-items: center; gap: 16px"><div style="flex: 1; display: flex; justify-content: center">'
            f'<div style="width: {pct}%; background: {bg}; color: {fg}; border-radius: 4px; padding: 12px 16px; text-align: center; font-size: 16px; box-sizing: border-box">{t}</div></div>{n}</div>')

def loopcard(t, d):
    return (f'<div style="{TINT}; padding: 12px 14px; flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px">'
            f'<span style="font-size: 15px">{t}</span><span style="font-size: 13px; line-height: 18px; color: {MUTED}">{d}</span></div>')

def where_row(w, r, c, shade):
    bg = "#F2F8FF" if shade else "#FFFFFF"
    return (f'<div style="display: grid; grid-template-columns: 150px minmax(0, 1fr) 110px; gap: 12px; padding: 9px 12px; background: {bg}; border-bottom: 1px solid {GREY2}; font-size: 15px; line-height: 20px">'
            f'<span>{w}</span><span>{r}</span><span style="color: {MUTED}">{c}</span></div>')

def rule(t):
    return (f'<div style="display: flex; gap: 10px; font-size: 15px; line-height: 21px"><span style="width: 10px; height: 10px; background: {LIME}; border: 1px solid {NAVY}; margin-top: 5px; flex: none"></span><span>{t}</span></div>')

group_rows = [("Syslog", "ProcessName"), ("CommonSecurityLog", "DeviceVendor + DeviceProduct"),
              ("Custom _CL with RawData", "Source tag or first token of the line"),
              ("Custom _CL with JSON", "Schema fingerprint: sorted list of keys")]
groups = "".join(
    f'<div style="display: grid; grid-template-columns: 230px 28px minmax(0, 1fr); align-items: center; gap: 8px">'
    f'{chip(a, "#FFFFFF", NAVY, True, GREY2)}{right()}<span style="font-size: 15px">{b}</span></div>' for a, b in group_rows)

def stack(lbl, a, b_, c):
    return (f'<div style="display: grid; grid-template-columns: 120px minmax(0, 1fr); gap: 12px; align-items: center">'
            f'<span style="font-size: 14px">{lbl}</span><div style="display: flex; height: 22px; border-radius: 3px; overflow: hidden">'
            f'<div style="width: {a}%; background: {BLUE}"></div><div style="width: {b_}%; background: {SKY}"></div><div style="width: {c}%; background: #E4E4E8"></div></div></div>')
stack_rows = stack("First pass", 20, 55, 25) + stack("After a month", 55, 35, 10) + stack("After a quarter", 75, 20, 5)

b10_body = f'''
<div style="display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr); gap: 28px">
<div style="display: flex; flex-direction: column; gap: 8px">
{label("Effort follows formats, not hosts")}
{funnel("Hosts and devices sending raw logs", 100, "#F1F1F3", NAVY)}
{funnel("Distinct programs and vendors", 84, PALE, NAVY)}
{funnel("Message templates worth mapping", 68, SKY, NAVY)}
{funnel("Fixed index columns", 52, BLUE, "#FFFFFF")}
<div style="font-size: 13px; color: {MUTED}">Widths show direction, not measured counts.</div>
</div>
<div style="display: flex; flex-direction: column; gap: 10px">
{label("Group sources by grammar")}
{groups}
<div style="font-size: 14px; line-height: 19px; color: {MUTED}">500 web servers running the same sshd share one set of templates.</div>
</div>
</div>
<div style="display: flex; flex-direction: column; gap: 8px">
{label("Shrink the unmatched share every week")}
<div style="display: flex; gap: 4px; align-items: stretch">
{loopcard("Unmatched lines", "Rows that only reached value regex")}{right()}
{loopcard("Mine templates", "Notebook runs Drain3 per grammar group")}{right()}
{loopcard("Rank by volume", "Largest new templates first")}{right()}
{loopcard("Analyst maps fields", "Approves the template and its ASIM fields")}{right()}
{loopcard("Generator rebuilds jobs", "KQL jobs regenerated from Git")}
</div>
<div style="display: flex; align-items: center; gap: 10px; padding: 0 8px"><div style="flex: 1; height: 0; border-top: 2px dashed {BLUE}"></div><span style="font-size: 14px; color: {BLUE}">Repeat: each pass moves the largest remaining formats from Tier 2 to Tier 1</span><div style="flex: 1; height: 0; border-top: 2px dashed {BLUE}"></div></div>
</div>
<div style="display: flex; flex-direction: column; gap: 8px">
{label("Where raw lines land, pass by pass")}
{stack_rows}
<div style="display: flex; gap: 20px; font-size: 13px; color: {MUTED}; align-items: center"><span style="display: flex; gap: 6px; align-items: center"><span style="width: 12px; height: 12px; background: {BLUE}"></span>Tier 1: template matched</span><span style="display: flex; gap: 6px; align-items: center"><span style="width: 12px; height: 12px; background: {SKY}"></span>Tier 2: value regex only</span><span style="display: flex; gap: 6px; align-items: center"><span style="width: 12px; height: 12px; background: #E4E4E8"></span>Tier 3: search only</span><span>Illustrative shares, not measured.</span></div>
</div>
<div style="display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr); gap: 28px">
<div style="display: flex; flex-direction: column">
{label("What runs where")}
<div style="height: 8px"></div>
{where_row("Template mining", "Spark notebook", "Weekly", True)}
{where_row("Index build", "One KQL job per grammar group", "Hourly or daily", False)}
{where_row("History backfill", "Spark notebook", "On demand", True)}
{where_row("Coverage report", "KQL job or notebook", "Each build", False)}
{where_row("Hunting", "Entity index, interactive or MCP", "Any time", True)}
</div>
<div style="display: flex; flex-direction: column; gap: 10px">
{label("Rules that keep it fast")}
{rule("Filter on the grouping key and a <span style='font-family: Consolas, monospace'>has</span> term before any regex.")}
{rule("One job per grammar group, never one per host.")}
{rule("Unmatched lines always go to value regex, so nothing is dropped.")}
{rule("Stagger job schedules to stay inside the tenant job quota.")}
{rule("Rebuild jobs from the registry; never hand-edit them.")}
</div>
</div>
'''
boards.append(("10-scaling-raw-sources", "Scaling to many raw sources",
               "Scaling to hundreds of raw log sources",
               "Maintain templates and a generator, not queries. Effort grows with formats, not hosts.",
               b10_body, "Microsoft Learn, data lake KQL jobs and notebooks; LevelBlue design"))

# ---------- write ----------
names = []
for i, (slug, short, title, sub, body, src) in enumerate(boards, 1):
    fname = "Main.dc.html" if i == 1 else f"{slug}.dc.html"
    names.append((fname, f"{i:02d} {short}", slug))
    with open(os.path.join(OUT, fname), "w", encoding="utf-8") as f:
        f.write(page(i, title, sub, body, src, f"{i:02d} {short}"))

canvas = {
    "v": 3,
    "createdOnFiles": {"v": 1, "at": "2026-10-16T11:55:50Z"},
    "title": "Sentinel Data Lake Normalization",
    "launch": {"view": "canvas"},
    "pages": [],
    "boards": {},
    "order": [],
    "notes": {},
    "designSystems": [],
}
for i, (fname, t, slug) in enumerate(names):
    canvas["boards"][fname] = {"x": (i % 4) * (W + 80), "y": (i // 4) * (H + 120), "w": W, "h": H, "title": t}
    canvas["order"].append(fname)
with open(os.path.join(OUT, "canvas.json"), "w", encoding="utf-8") as f:
    json.dump(canvas, f, indent=1)
with open(os.path.join(HERE, "boards.json"), "w", encoding="utf-8") as f:
    json.dump(names, f, indent=1)
print("\n".join(n[0] for n in names))
