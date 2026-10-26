"""Opening chapter of the demo video: the architecture building blocks, revealed one step at a time.

Every claim here matches the shipped kit: notebook 01 runs daily over every lake table (field inventory and
template mining), proposals feed the review in Lake Hunt, an Admin approves, KQL jobs and notebook 02 index
hourly, notebook 03 measures coverage daily.
"""
from __future__ import annotations

# (step number, caption) in the order they are shown; each step reveals the elements marked data-step="<n>".
STEPS = [
    (1, "Hundreds of tables land in the Sentinel data lake, each with its own field names."),
    (2, "Every day, a scan samples recent rows of every table and records each field: its type, how full it is, and what its values look like."),
    (3, "New tables and fields appear in Lake Hunt as proposals, table by table, for a person to confirm."),
    (4, "An Admin approves each mapping. Nothing reaches the tenant before that."),
    (5, "Approved mappings become hourly index jobs that write one hunt index with ASIM field names."),
    (6, "A daily coverage check flags drift when a vendor changes its log format, and sends the source back for review."),
    (7, "Here is that cycle in the app."),
]

HTML = r"""<!doctype html><html><head><meta charset="utf-8"><style>
*{box-sizing:border-box} body{margin:0;width:1440px;height:900px;background:#F6F8FC;color:#05052F;font-family:Arial,sans-serif;overflow:hidden;position:relative}
h1{position:absolute;left:80px;top:34px;margin:0;font-size:34px;font-weight:400;color:#001AFF}
.sub{position:absolute;left:80px;top:84px;font-size:18px;color:#6B6E8A}
.box{position:absolute;background:#fff;border:1.5px solid #DCDCDD;border-radius:14px;padding:18px 22px;box-shadow:0 2px 10px rgba(5,5,47,.06);
  opacity:0;transform:translateY(10px);transition:opacity .6s,transform .6s,border-color .4s,box-shadow .4s}
.box.on{opacity:1;transform:none}
.box.focus{border-color:#001AFF;box-shadow:0 0 0 3px rgba(0,26,255,.15),0 2px 10px rgba(5,5,47,.06)}
.box h2{margin:0 0 4px;font-size:21px} .box .k{font-size:13px;color:#6B6E8A;margin-bottom:12px;text-transform:uppercase;letter-spacing:.5px;font-weight:700}
.box ul{margin:0;padding-left:18px;font-size:16px;line-height:1.55;color:#3D3F5C}
.chip{display:flex;justify-content:space-between;align-items:center;border:1px solid #DCDCDD;border-radius:9px;padding:9px 12px;margin-bottom:9px;font:15px Consolas,monospace;background:#EEF4FB}
.new{font:700 11px Arial;background:#CAFF00;color:#05052F;border-radius:5px;padding:2px 7px;opacity:0;transition:opacity .5s}
.new.on{opacity:1}
.more{font-size:15px;color:#6B6E8A;text-align:center;margin-top:6px}
table{border-collapse:collapse;width:100%;font-size:15px} td{padding:6px 4px;border-top:1px solid #EEF0F5} td:first-child{font-family:Consolas,monospace}
.who{margin-top:10px;font-size:14px;color:#3D3F5C} .who b{color:#001AFF}
.ok{display:inline-block;margin-top:10px;font:700 14px Arial;color:#0B6E0B;background:#E7F6E7;border-radius:99px;padding:3px 12px;opacity:0;transition:opacity .5s}
.ok.on{opacity:1}
svg{position:absolute;left:0;top:0;width:1440px;height:900px;pointer-events:none}
.arrow{fill:none;stroke:#A5A5A5;stroke-width:2.5;stroke-dasharray:1;stroke-dashoffset:1;opacity:0;transition:stroke-dashoffset 1s ease,opacity .2s}
.arrow.on{stroke-dashoffset:0;opacity:1}
.arrow.loop{stroke:#001AFF;stroke-dasharray:8 6;stroke-dashoffset:0;opacity:0;transition:opacity .8s}
.arrow.loop.on{opacity:1}
.lbl{font:600 14px Arial;fill:#6B6E8A;opacity:0;transition:opacity .6s} .lbl.on{opacity:1}
#cap{position:absolute;left:50%;bottom:28px;transform:translateX(-50%);width:1100px;background:rgba(5,5,47,.93);color:#fff;font:600 22px/1.35 Arial,sans-serif;
  padding:14px 26px;border-radius:12px;border-left:6px solid #CAFF00;box-shadow:0 8px 30px rgba(0,0,0,.35)}
#cap:empty{display:none}
</style></head><body>
<h1>How Lake Hunt works</h1><div class="sub">The building blocks, and the cycle that keeps every source searchable with ASIM field names</div>

<div class="box" data-step="1" id="lake" style="left:80px;top:140px;width:320px;height:470px">
  <div class="k">Microsoft Sentinel</div><h2>Data lake tables</h2><div style="height:12px"></div>
  <div class="chip">SigninLogs</div><div class="chip">CommonSecurityLog</div><div class="chip">Syslog</div>
  <div class="chip">AWSCloudTrail</div><div class="chip">OktaV2_CL</div>
  <div class="chip">BadgeReader_CL <span class="new" data-step="2">new</span></div>
  <div class="more">… hundreds more</div></div>

<div class="box" data-step="2" id="scan" style="left:490px;top:140px;width:400px;height:262px">
  <div class="k">Daily · notebook 01</div><h2>Scan for new fields</h2>
  <ul><li>Samples recent rows of every table</li><li>Finds fields in columns, JSON and key=value text</li><li>Records type, fill rate and what the values look like</li><li>Mines message templates from raw text</li></ul></div>

<div class="box" data-step="3" id="review" style="left:980px;top:140px;width:390px;height:330px">
  <div class="k">Lake Hunt</div><h2>New fields, per table</h2>
  <div style="font:600 15px Consolas,monospace;margin:8px 0 4px">BadgeReader_CL</div>
  <table><tr><td>holder</td><td>user · who did it</td></tr><tr><td>reader</td><td>IP · reporting device</td></tr><tr><td>result</td><td>success / failure</td></tr></table>
  <div class="who">An analyst confirms each proposal</div>
  <div class="ok" data-step="4">Admin approved · audit logged</div></div>

<div class="box" data-step="5" id="jobs" style="left:980px;top:530px;width:390px;height:180px">
  <div class="k">Hourly · KQL jobs and notebook 02</div><h2>Index jobs</h2>
  <ul><li>Read the lake tables</li><li>Apply the approved mappings</li></ul></div>

<div class="box" data-step="5" id="index" style="left:490px;top:530px;width:400px;height:180px">
  <div class="k">One table, ASIM field names</div><h2>Hunt index</h2>
  <ul><li>Entity, role, source</li><li>A key back to the original row</li></ul></div>

<div class="box" data-step="6" id="cov" style="left:490px;top:420px;width:400px;height:80px;padding:14px 22px">
  <div class="k" style="margin:0">Daily · notebook 03</div><h2 style="font-size:18px">Coverage and drift check</h2></div>

<svg viewBox="0 0 1440 900">
  <defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#A5A5A5"/></marker>
        <marker id="ab" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#001AFF"/></marker></defs>
  <path class="arrow" pathLength="1" data-step="2" d="M402 250 H486" marker-end="url(#ah)"/>
  <path class="arrow" pathLength="1" data-step="3" d="M892 250 H976" marker-end="url(#ah)"/>
  <text class="lbl" data-step="3" x="900" y="238">proposals</text>
  <path class="arrow" pathLength="1" data-step="5" d="M1175 472 V526" marker-end="url(#ah)"/>
  <path class="arrow" pathLength="1" data-step="5" d="M978 620 H894" marker-end="url(#ah)"/>
  <path class="arrow" pathLength="1" data-step="5" d="M240 612 V760 H1175 V714" marker-end="url(#ah)"/>
  <text class="lbl" data-step="5" x="600" y="752">index jobs read the lake tables</text>
  <path class="arrow" pathLength="1" data-step="6" d="M690 528 V502" marker-end="url(#ah)"/>
  <path class="arrow loop" data-step="6" d="M892 460 H935 V420 H976" marker-end="url(#ab)"/>
  <text class="lbl" data-step="6" x="900" y="410">drift → review</text>
</svg>
<div id="cap"></div>
<script>
window.step = (n, text) => {
  document.querySelectorAll(".focus").forEach((e) => e.classList.remove("focus"));
  document.querySelectorAll(`[data-step="${n}"]`).forEach((e) => { e.classList.add("on"); if (e.classList.contains("box")) e.classList.add("focus"); });
  document.getElementById("cap").textContent = text || "";
};
</script></body></html>"""


def play(page, flow) -> None:
    """Show the architecture chapter, one step per caption."""
    page.set_content(HTML)
    page.wait_for_timeout(600)
    for n, text in STEPS:
        page.evaluate("([n, t]) => window.step(n, t)", [n, text])
        flow.wait(4.5 if len(text) > 80 else 3.5)
