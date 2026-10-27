"""Render the architecture diagrams (diagrams/architecture.png and blog/img/03-architecture.png).

Each diagram is a list of boxes, bands, labels and arrows in CSS pixels on a 672 px wide canvas,
rendered by Chromium at 2x. Run from the repo root:  python diagrams/build_diagrams.py
"""
from __future__ import annotations

import html
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
W = 672
LINE = "#bfbdb5"


def box(x, y, w, h, title, sub="", kind="plain", align="center", size=15):
    return ("box", dict(x=x, y=y, w=w, h=h, title=title, sub=sub, kind=kind, align=align, size=size))


def band(x, y, w, h):
    return ("band", dict(x=x, y=y, w=w, h=h))


def label(x, y, text, size=13, weight=400, color="#444", anchor="start", w=300):
    return ("label", dict(x=x, y=y, text=text, size=size, weight=weight, color=color, anchor=anchor, w=w))


def arrow(*pts, head=True):
    return ("arrow", dict(pts=pts, head=head))


def render(items: list, height: int) -> str:
    divs, paths = [], []
    for kind, a in items:
        if kind == "band":
            divs.append(f'<div class="band" style="left:{a["x"]}px;top:{a["y"]}px;width:{a["w"]}px;height:{a["h"]}px"></div>')
        elif kind == "box":
            sub = f'<div class="sub">{a["sub"]}</div>' if a["sub"] else ""
            ta = "left" if a["align"] == "left" else "center"
            divs.append(f'<div class="box {a["kind"]}" style="left:{a["x"]}px;top:{a["y"]}px;width:{a["w"]}px;height:{a["h"]}px;'
                        f'text-align:{ta};justify-content:{"flex-start" if a["align"] == "top" else "center"}">'
                        f'<div class="t" style="font-size:{a["size"]}px">{a["title"]}</div>{sub}</div>')
        elif kind == "label":
            left = a["x"] - (a["w"] if a["anchor"] == "end" else a["w"] / 2 if a["anchor"] == "middle" else 0)
            ta = {"start": "left", "end": "right", "middle": "center"}[a["anchor"]]
            divs.append(f'<div class="lab" style="left:{left}px;top:{a["y"]}px;width:{a["w"]}px;text-align:{ta};'
                        f'font-size:{a["size"]}px;font-weight:{a["weight"]};color:{a["color"]}">{html.escape(a["text"])}</div>')
        else:
            d = "M" + " L".join(f"{x} {y}" for x, y in a["pts"])
            paths.append(f'<path d="{d}" fill="none" stroke="{LINE}" stroke-width="1.3"'
                         f'{" marker-end=\"url(#h)\"" if a["head"] else ""}/>')
    svg = (f'<svg width="{W}" height="{height}" style="position:absolute;left:0;top:0;z-index:1"><defs>'
           f'<marker id="h" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">'
           f'<path d="M0 0L10 5L0 10z" fill="{LINE}"/></marker></defs>{"".join(paths)}</svg>')
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
body{{margin:0;background:#fff;font-family:Inter,Arial,sans-serif;color:#151515}}
#c{{position:relative;width:{W}px;height:{height}px;overflow:hidden}}
.band{{position:absolute;background:#efeeeb;border-radius:9px;z-index:0}}
.box{{position:absolute;box-sizing:border-box;background:#fff;border:1.3px solid #cfcdc6;border-radius:8px;z-index:2;
     display:flex;flex-direction:column;align-items:stretch;padding:4px 6px;gap:2px}}
.box.grey{{background:#efeeeb}}
.box.hi{{background:#e7effa;border:2px solid #2f7ad8}}
.box.inner{{background:#f6f5f2}}
.t{{font-weight:600;line-height:1.2;white-space:nowrap}}
.sub{{font-size:10.5px;color:#55534d;line-height:1.35;white-space:nowrap}}
.lab{{position:absolute;z-index:3;line-height:1.3;white-space:nowrap}}
</style></head><body><div id="c">{"".join(divs)}{svg}</div></body></html>"""


def blog_architecture() -> tuple[list, int]:
    """Short version for the blog: sources, mapping, the two index tables, hunting, and the loop below."""
    it = [label(21, 14, "Hundreds of sources, one index, one set of field names", 17, 600, "#151515", w=640),
          label(81, 50, "Sources in the lake", 12, 600, "#555", "middle", 160),
          label(267, 50, "Mapping", 12, 600, "#555", "middle", 160),
          label(454, 50, "Lake index", 12, 600, "#555", "middle", 160),
          label(597, 50, "Hunting", 12, 600, "#555", "middle", 160)]
    for i, name in enumerate(["Native tables", "CEF", "JSON tables", "Syslog text", "Raw text"]):
        y = 72 + i * 33
        it.append(box(21, y, 120, 26, name, size=12.5))
        it.append(arrow((141, y + 13), (169, y + 13)))
    it += [box(170, 70, 194, 162, "", kind="grey"),
           label(267, 77, "Index builders, hourly", 11.5, 600, "#555", "middle", 194),
           box(183, 97, 168, 56, "KQL jobs", "approved groups,<br>one job per source table", kind="inner", size=12.5),
           box(183, 163, 168, 56, "Lake notebook", "groups still under review,<br>templates, classifier", kind="inner", size=12.5),
           box(392, 82, 124, 54, "HuntEntity", "hourly entity counts,<br>plus job counts", kind="hi", size=12.5),
           box(392, 150, 124, 54, "HuntEvent", "ASIM-shaped events,<br>Tier 1 sources", kind="hi", size=12.5),
           box(544, 85, 106, 48, "AI agent", "data lake MCP", size=12.5),
           box(544, 153, 106, 48, "Analysts", "advanced hunting", size=12.5),
           arrow((364, 109), (391, 109)), arrow((364, 177), (391, 177)),
           arrow((516, 109), (543, 109)), arrow((516, 177), (543, 177)),
           box(21, 268, 156, 54, "Notebook 01", "reads only new or changed<br>tables and drifting groups", size=12.5),
           box(201, 268, 152, 54, "Registry in Git", "proposed, reviewed,<br>then approved", size=12.5),
           box(392, 268, 124, 54, "Notebook 03", "coverage from the<br>job counts", size=12.5),
           arrow((81, 237), (81, 267)), arrow((177, 295), (200, 295)), arrow((267, 268), (267, 233)),
           arrow((454, 204), (454, 267)), arrow((392, 295), (354, 295)),
           label(528, 270, "Drift: when more than 5% of", 10.5, 400, "#6a675f", "start", 140),
           label(528, 284, "an approved group's lines", 10.5, 400, "#6a675f", "start", 140),
           label(528, 298, "stop matching, notebook 01", 10.5, 400, "#6a675f", "start", 140),
           label(528, 312, "mines just those lines", 10.5, 400, "#6a675f", "start", 140)]
    return it, 340


def full_architecture() -> tuple[list, int]:
    """Tall version for the repo: every layer from lake tables to the agent."""
    rows = [("Lake tables", 88), ("Mapping", 205), ("Build", 290), ("Run hourly", 375), ("Lake index", 449),
            ("Hunt", 530), ("Ask", 612)]
    it = [label(21, 14, "Hundreds of sources become two tables and one set of hunt tools", 17, 600, "#151515", w=640),
          band(14, 43, 644, 91), band(14, 417, 644, 64)]
    it += [label(21, y - 9, t, 13, 400, "#444") for t, y in rows]
    for i, (t, s) in enumerate([("Typed columns", "SecurityEvent, Signin<br>key: table + EventID"),
                                ("CEF", "CommonSecurityLog<br>key: vendor+product"),
                                ("Syslog, raw text", "Syslog, RawData<br>key: ProcessName"),
                                ("Custom JSON _CL", "app and SaaS tables<br>key: JSON key set")]):
        x = 106 + i * 139
        it.append(box(x, 50, 128, 77, t, s, kind="grey", size=12.5))
        it.append(arrow((x + 64, 127), (x + 64, 132), head=False))
    it += [arrow((170, 132), (586, 132), head=False),
           label(106, 140, "Tens of grammar groups, one registry entry each", 11.5, 400, "#444", w=300),
           label(565, 147, "new or changed tables only", 11.5, 400, "#444", "end", 200),
           arrow((586, 132), (586, 172)),
           box(106, 173, 159, 64, "ASIM parser YAML", "Microsoft parsers<br>via asim_expand.py", size=12.5),
           box(299, 173, 159, 64, "Registry in Git", "rules, templates, roles;<br>status: proposed or approved",
               kind="hi", size=12.5),
           box(492, 173, 158, 64, "Notebook 01, daily", "inventory, and templates<br>from unmatched lines", size=12.5),
           arrow((265, 205), (298, 205)), arrow((492, 205), (459, 205)),
           arrow((378, 237), (378, 264)),
           box(299, 265, 159, 50, "generate.py", "plain KQL, one job per table", size=12.5),
           arrow((378, 315), (378, 332), head=False), arrow((199, 332), (558, 332), head=False),
           arrow((199, 332), (199, 349)), arrow((558, 332), (558, 349)),
           label(206, 335, "approved", 11, 400, "#6a675f", w=80),
           label(551, 335, "proposed", 11, 400, "#6a675f", "end", 80),
           box(106, 350, 186, 50, "KQL jobs", "approved groups, one per table", size=12.5),
           box(465, 350, 185, 50, "Notebook 02", "groups still under review", size=12.5),
           arrow((199, 400), (199, 423)), arrow((558, 400), (558, 412), head=False),
           arrow((199, 412), (558, 412), head=False), arrow((412, 412), (412, 423)),
           box(106, 424, 195, 50, "HuntEntity_SPRK", "hourly rollup, every source", kind="hi", size=12.5),
           box(315, 424, 194, 50, "HuntEvent_SPRK", "ASIM rows, Tier 1 sources", kind="grey", size=12.5),
           box(523, 424, 127, 50, "HuntCoverage", "notebook 03,<br>from job counts", kind="grey", size=12.5),
           arrow((203, 474), (203, 504)), arrow((412, 474), (412, 504)), arrow((587, 474), (587, 504)),
           box(106, 505, 544, 50, "Data lake MCP: 7 fixed tools",
               "hunt_value, hunt_entity (sum of hourly counts), auth_events, network_events, coverage;<br>"
               "pivot_raw and search_raw read raw tables", size=12.5),
           arrow((378, 555), (378, 586)),
           box(281, 587, 194, 50, "Agent or analyst", "one schema, every source", size=12.5)]
    return it, 660


def main() -> None:
    out = [(blog_architecture, ROOT / "blog" / "img" / "03-architecture.png"),
           (full_architecture, ROOT / "diagrams" / "architecture.png")]
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        for fn, path in out:
            items, h = fn()
            page = b.new_page(viewport={"width": W, "height": h}, device_scale_factor=2)
            page.set_content(render(items, h))
            page.wait_for_timeout(200)
            page.locator("#c").screenshot(path=str(path))
            print("wrote", path.relative_to(ROOT))
        b.close()


if __name__ == "__main__":
    main()
