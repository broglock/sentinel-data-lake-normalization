/* More: reference screens for setup and administration. */
import { ROUTES, $, $$, api, esc, num, pct, when, enc, ME, can, demoRole, toast, st, tier, layerTag, modal, jsyaml, pageHeader, disclose, renderNav, refreshPending, router, MORE_NAV } from "./core.js";
import { barChart, spark } from "./charts.js";

// same rule as kit/generate.py engine_of: approved groups run in KQL jobs, the rest in the notebook
const engineOf = (g) => (g.status ? (g.status === "approved" ? "kql_job" : "notebook") : g.engine || "notebook");

ROUTES.more = async (main) => {
  main.innerHTML = pageHeader("More", "Reference screens for setup and administration.") +
    `<div class="tasks">${MORE_NAV.filter(([, , r]) => can(r)).map(([k, label, , d]) => `<a class="task" href="#/${k}"><h2>${esc(label)}</h2><p class="muted">${esc(d)}</p></a>`).join("")}</div>`;
};

ROUTES.about = async (main) => {
  const c = (await api("/overview")).catalog;
  main.innerHTML = pageHeader("Why an index", `From the Microsoft Sentinel content catalog (${esc(c.solutions)} solutions).`) + `
    <div class="card"><div class="grid g2">
      <div class="kpi"><span class="v">${num(c.tables)}</span><span class="l">tables written by ${num(c.connectors)} data connectors</span></div>
      <div class="kpi"><span class="v">${num(c.tablesWithAsim)}</span><span class="l">of those tables have an ASIM parser (${pct(c.tablesWithAsim / c.tables, 1)})</span></div></div>
      <div class="callout" style="margin-top:14px">ASIM parsers are stored functions and lake KQL does not run them. Lake Hunt applies ASIM logic where Microsoft ships it, registry rules and templates everywhere else, and a value classifier as the floor, so every table is searchable with one set of field names.</div></div>`;
};

// ------------------------------------------------------------------ connector catalog
ROUTES.catalog = async (main, arg) => {
  if (arg) return renderPlan(main, arg);
  const params = new URLSearchParams(location.search);
  main.innerHTML = `
    ${pageHeader("Connectors", "Every data connector in the Content hub, the tables it writes, and whether an ASIM parser exists.")}
    <div class="card"><div class="row">
      <input class="search" type="search" id="q" placeholder="Search solutions, connectors or tables (e.g. okta, CommonSecurityLog)">
      <select id="asim"><option value="">ASIM parser: any</option><option value="yes">Has ASIM parser</option><option value="no">No ASIM parser</option></select>
      <select id="kind"><option value="">Tables: any</option><option value="custom">Custom tables (_CL)</option><option value="native">Built-in tables only</option></select>
      <span class="muted small right" id="cstats"></span></div>
      <div id="results" style="margin-top:12px"></div></div>`;
  let page = 1;
  const load = async () => {
    const r = await api(`/catalog/solutions?q=${enc($("#q").value)}&asim=${$("#asim").value}&kind=${$("#kind").value}&page=${page}&size=40`);
    $("#cstats").textContent = `${num(r.total)} of ${num(r.stats.solutions)} solutions · catalog ${r.commit} (${r.built})`;
    $("#results").innerHTML = `<div class="tbl-wrap"><table><tr><th>Solution</th><th>Tables</th><th>ASIM coverage</th><th>Mapping path</th><th>Status</th></tr>
      ${r.items.map((s) => `<tr class="click" onclick="location.hash='#/catalog/${enc(s.folder)}'"><td><b>${esc(s.name)}</b><div class="muted small">${esc(s.author)} ${s.version ? "· v" + esc(s.version) : ""} · ${s.connectors} connector${s.connectors > 1 ? "s" : ""}${s.deprecatedOnly ? " · deprecated" : ""}</div></td>
      <td>${s.tables.slice(0, 4).map((t) => `<span class="tag">${esc(t)}</span>`).join("")}${s.tables.length > 4 ? `<span class="muted small">+${s.tables.length - 4}</span>` : ""}</td>
      <td>${s.asimTables.length ? `<span class="tag asim">${s.asimTables.length} of ${s.tables.length} tables</span>` : `<span class="muted small">none</span>`}</td>
      <td>${esc({ asim: "ASIM logic", mixed: "ASIM + review", registry: "Field review" }[s.path])}</td>
      <td>${s.installed ? st("ok", "installed") : ""}</td></tr>`).join("")}</table></div>
      <div class="row" style="margin-top:10px"><button class="btn sm" id="prev" ${page <= 1 ? "disabled" : ""}>← Previous</button><span class="small muted">Page ${page} of ${Math.max(1, Math.ceil(r.total / 40))}</span><button class="btn sm" id="next" ${page * 40 >= r.total ? "disabled" : ""}>Next →</button></div>`;
    $("#prev").onclick = () => { page--; load(); };
    $("#next").onclick = () => { page++; load(); };
  };
  let t;
  $("#q").addEventListener("input", () => { clearTimeout(t); t = setTimeout(() => { page = 1; load(); }, 250); });
  $("#asim").onchange = $("#kind").onchange = () => { page = 1; load(); };
  if (params.get("q")) $("#q").value = params.get("q");
  await load();
};

async function renderPlan(main, folder) {
  const p = await api(`/catalog/solutions/${enc(folder)}/plan`);
  main.innerHTML = `
    <p><a href="#/catalog">← Connectors</a></p>
    ${pageHeader(p.solution.name, `${esc(p.solution.author)}. Plan where each table lives, then request the deployment.`)}
    <div class="grid g2">
      <div class="card"><h2>Data connectors</h2>${p.connectors.map((c) => `<div style="margin-bottom:8px"><b>${esc(c.title)}</b> <span class="tag">${esc(c.kind)}</span>${c.deprecated ? st("warn", "deprecated") : ""}<div class="small muted">${c.tables.map(esc).join(", ")}</div></div>`).join("")}</div>
      <div class="card"><h2>What happens on approval</h2>
        <ol class="small" style="padding-left:18px;margin:0">
          <li>The solution is installed from the Content hub (connector definitions, parsers, content).</li>
          <li>Custom tables with a known schema are created on the plan you choose below.</li>
          <li>Built-in tables are created by Microsoft when the connector sends data.</li>
        </ol><hr><h3>Still done by a person</h3><ul class="small" style="padding-left:18px;margin:0">${p.manualSteps.map((s) => `<li>${esc(s)}</li>`).join("")}</ul></div>
    </div>
    <div class="card" style="margin-top:16px"><h2>Tables</h2>
      <p class="hint">Recommended plan: Analytics for tables that drive detections and already have ASIM parsers; Lake for everything kept for hunting and retention. Lake Hunt indexes both.</p>
      <div class="tbl-wrap"><table><tr><th>Create</th><th>Table</th><th>Plan</th><th>Created by</th><th>Mapping path</th><th>ASIM parsers</th></tr>
      ${p.tables.map((t, i) => `<tr><td>${t.custom && t.schemaKnown && !t.exists ? `<input type="checkbox" data-t="${i}" checked aria-label="create ${esc(t.name)}">` : t.exists ? st("ok", "exists") : ""}</td>
        <td><b>${esc(t.name)}</b><div class="small muted">${t.columns.length ? t.columns.length + " columns known" : ""}</div></td>
        <td><select data-plan="${i}"><option ${t.recommendedPlan === "Analytics" ? "selected" : ""}>Analytics</option><option ${t.recommendedPlan === "Lake" ? "selected" : ""}>Lake</option></select><div class="small muted" style="max-width:240px">${esc(t.planReason)}</div></td>
        <td class="small">${esc(t.createdBy)}</td><td class="small">${esc(t.mappingPath)}</td>
        <td>${t.asimParsers.slice(0, 3).map((x) => `<span class="tag asim">${esc(x)}</span>`).join("")}${t.asimParsers.length > 3 ? `<span class="small muted">+${t.asimParsers.length - 3}</span>` : ""}</td></tr>`).join("")}</table></div>
      <div class="row" style="margin-top:12px"><label class="inline"><input type="checkbox" id="inst" checked> Install the solution</label>
      <label class="inline">Retention <input type="number" id="ret" value="365" min="30" max="4383" style="width:90px"> days</label>
      <button class="btn primary right" id="req" ${can("analyst") ? "" : "disabled"}>Request deployment</button></div></div>`;
  $("#req").onclick = async () => {
    const tables = $$("[data-t]").filter((c) => c.checked).map((c) => {
      const t = p.tables[+c.dataset.t];
      return { name: t.name, columns: t.columns, plan: $(`[data-plan="${c.dataset.t}"]`).value, retentionDays: +$("#ret").value };
    });
    const body = { solutions: $("#inst").checked ? [{ name: p.solution.name, version: p.solution.version }] : [], tables };
    try { const r = await api("/deployments", { method: "POST", body }); toast(`Approval #${r.approval} requested`); await refreshPending(); if (can("admin")) location.hash = "#/approve"; }
    catch (e) { toast(e.message, true); }
  };
}

// ------------------------------------------------------------------ registry
ROUTES.registry = async (main, gid) => {
  if (gid) {
    const [r, hist] = await Promise.all([api(`/registry/${enc(gid)}`), api(`/registry/${enc(gid)}/history`)]);
    const g = r.group;
    main.innerHTML = `<p><a href="#/registry">← Registry</a></p>${pageHeader(gid, `${st(r.status)} version ${r.version}, last changed by ${esc(r.updated_by)} at ${when(r.updated_at)}`)}
      <div class="grid g2"><div class="card"><h2>Definition</h2><dl class="kv"><dt>Table</dt><dd>${esc(g.table)}</dd><dt>Filter</dt><dd class="mono">${esc(g.filter)}</dd><dt>Schema</dt><dd>${esc(g.schema || "–")}</dd><dt>Engine</dt><dd>${esc(engineOf(g))}</dd><dt>Mapped by</dt><dd>${layerTag(g.layer || "registry")}</dd><dt>Fields</dt><dd>${(g.fields || []).map((f) => `<span class="tag">${esc(f.column || f.path)} → ${esc(f.asim || f.entity + ":" + f.role)}</span>`).join("") || "–"}</dd><dt>Templates</dt><dd>${(g.templates || []).length}</dd></dl>
        <div class="row" style="margin-top:12px"><a class="btn" href="#/review/${enc(g.table)}">Open field review</a>${r.status === "draft" && can("analyst") ? `<button class="btn primary" id="sub">Submit for approval</button>` : ""}${r.status === "live" ? `<a class="btn" href="#/validation/${enc(gid)}">Validate</a>` : ""}${r.status !== "retired" && can("admin") ? `<button class="btn danger" id="ret">Retire</button>` : ""}</div></div>
      <div class="card"><h2>YAML</h2><pre>${esc(jsyaml(g))}</pre></div></div>
      <div class="card" style="margin-top:16px"><h2>History</h2><div class="tbl-wrap"><table><tr><th>Version</th><th>Status</th><th>By</th><th>When</th><th>Note</th></tr>${hist.map((h) => `<tr><td>${h.version}</td><td>${st(h.status)}</td><td>${esc(h.by)}</td><td>${when(h.at)}</td><td>${esc(h.note)}</td></tr>`).join("")}</table></div></div>`;
    if ($("#sub")) $("#sub").onclick = async () => { try { const x = await api(`/registry/${enc(gid)}/submit`, { method: "POST" }); toast(`Approval #${x.approval} requested`); await refreshPending(); router(); } catch (e) { toast(e.message, true); } };
    if ($("#ret")) $("#ret").onclick = async () => { if (!confirm(`Retire ${gid}? The table falls back to the classifier.`)) return; await api(`/registry/${enc(gid)}/retire`, { method: "POST" }); router(); };
    return;
  }
  const rows = await api("/registry");
  main.innerHTML = `${pageHeader("Registry", "One entry per table and message format; the single definition every job builds from.", `<a class="btn" href="/api/v1/registry/export" target="_blank">Export YAML</a>`)}
    <div class="card"><div class="row"><span class="muted small">${rows.length} entries</span></div>
    <div class="tbl-wrap" style="margin-top:10px"><table><tr><th>Group</th><th>Table</th><th>Status</th><th>Mapped by</th><th>Engine</th><th>Tier</th><th class="num">Version</th><th>Changed</th></tr>
    ${rows.map((r) => `<tr class="click" onclick="location.hash='#/registry/${enc(r.id)}'"><td><b>${esc(r.id)}</b></td><td>${esc(r.group.table)}</td><td>${st(r.status)}</td><td>${layerTag(r.group.layer || "registry")}</td><td>${esc(engineOf(r.group))}</td><td>${tier(+r.group.tier || 1)}</td><td class="num">${r.version}</td><td>${when(r.updated_at)}</td></tr>`).join("")}</table></div></div>`;
};

// ------------------------------------------------------------------ build and deploy
ROUTES.deploy = async (main) => {
  const b = await api("/build");
  const pctUsed = b.budget.kqlJobs / b.budget.limit;
  main.innerHTML = `${pageHeader("Build and deploy", "Every KQL job, the notebook configuration and the MCP queries, generated from the live registry.", `<a class="btn primary" href="/api/v1/build/bundle.zip">Download bundle</a>`)}
    <div class="grid g3">
      <div class="card kpi"><span class="bar4"></span><span class="v">${b.budget.kqlJobs} <span class="muted" style="font-size:16px">/ ${b.budget.limit}</span></span><span class="l">KQL jobs (tenant limit)</span><div class="progress" style="margin-top:6px"><i style="width:${Math.min(100, pctUsed * 100)}%;background:${b.budget.warning ? "var(--warn)" : "var(--blue)"}"></i></div>${b.budget.warning ? `<span class="small">${st("warn", "over " + b.budget.soft)} move low-volume groups to the notebook</span>` : ""}</div>
      <div class="card kpi"><span class="bar4"></span><span class="v">${b.notebookGroups.length}</span><span class="l">groups indexed by the hourly notebook</span></div>
      <div class="card"><h2>Bundle</h2><p class="hint">Built ${when(b.built)}</p><div class="row"><a class="btn primary" href="/api/v1/build/bundle.zip">Download deployment bundle</a><button class="btn" id="runidx">${ME.mode === "demo" ? "Re-run index now" : "Check index status"}</button></div></div>
    </div>
    <div class="grid g2" style="margin-top:16px">
      <div class="card"><h2>KQL jobs to create</h2><div class="tbl-wrap"><table><tr><th>Job name</th><th>Group</th><th>Output table</th><th></th></tr>${b.jobs.map((j) => `<tr><td class="mono">${esc(j.name)}</td><td>${esc(j.group)}</td><td class="mono">${esc(j.output)}</td><td><button class="btn sm" data-file="${esc(j.file)}">View</button></td></tr>`).join("")}</table></div>
        <h3 style="margin-top:14px">Notebook groups</h3><div>${b.notebookGroups.map((g) => `<span class="tag">${esc(g)}</span>`).join("")}</div></div>
      <div class="card">${disclose("Portal steps", `<pre style="white-space:pre-wrap;max-height:none">${esc(b.files["DEPLOY.md"])}</pre>`)}</div>
    </div>`;
  $$("[data-file]").forEach((x) => (x.onclick = () => modal(x.dataset.file, `<pre style="max-height:70vh">${esc(b.files[x.dataset.file])}</pre>`)));
  $("#runidx").onclick = async () => { const r = await api("/index/run", { method: "POST" }); toast(r.message || `Indexed ${num(r.entityRows)} entity rows from ${r.groups} groups`); };
};

// ------------------------------------------------------------------ coverage
ROUTES.coverage = async (main, gid) => {
  const cov = await api("/coverage");
  main.innerHTML = `${pageHeader("Coverage", "How deeply each source is indexed; status turns to review below 90% extraction and 70% template match.")}
    <div class="card"><h2>Extraction rate by source</h2>${barChart(cov.slice().sort((a, b) => a.ExtractionRate - b.ExtractionRate).map((r) => ({ label: r.SourceGroup, value: r.ExtractionRate, status: r.Status, muted: r.Tier === 2, href: "#/coverage/" + enc(r.SourceGroup), note: `${num(r.RawRows)} raw rows · tier ${r.Tier}` })), { threshold: 0.9 })}</div>
    <div class="card section"><div class="tbl-wrap"><table><tr><th>Group</th><th>Tier</th><th>Mapped by</th><th class="num">Raw rows</th><th class="num">Extraction</th><th class="num">Template match</th><th class="num">No-role share</th><th>Last 7 days</th><th>Status</th><th></th></tr>
    ${cov.map((c, i) => `<tr><td><b>${esc(c.SourceGroup)}</b><div class="small muted">${esc(c.SourceTable)}</div></td><td>${tier(c.Tier)}</td><td>${layerTag(c.Layer || "")}</td><td class="num">${num(c.RawRows)}</td><td class="num">${pct(c.ExtractionRate, 1)}</td><td class="num">${c.TemplateMatchRate === null || c.TemplateMatchRate === undefined ? "–" : pct(c.TemplateMatchRate, 1)}</td><td class="num">${pct(c.UnknownRoleShare)}</td><td id="sp${i}"></td><td>${st(c.Status)}</td><td><button class="btn sm" data-drift="${esc(c.SourceGroup)}">Explain</button></td></tr>`).join("")}</table></div></div>
    <div class="card" style="margin-top:16px" id="drift"><h2>Explain a source</h2><div class="muted">Pick Explain on a row to see what the index misses in that source and why.</div></div>`;
  cov.forEach(async (c, i) => { try { const h = await api(`/coverage/${enc(c.SourceGroup)}/history`); const el = $("#sp" + i); if (el) el.innerHTML = `<span data-tip="${esc(h.map((d) => `${d.day}: ${d.extraction === null ? "no rows" : pct(d.extraction)}`).join("<br>"))}">${spark(h.map((d) => d.extraction))}</span>`; } catch { /* ignore */ } });
  const explain = async (id) => {
    const table = (cov.find((c) => c.SourceGroup === id) || {}).SourceTable || id.split(":")[0];
    const d = $("#drift"); d.innerHTML = `<h2>${esc(id)}</h2><div class="loader">Looking at recent rows…</div>`;
    try {
      const r = await api(`/coverage/${enc(id)}/history`);
      const x = await fetch(`/mcp`, { method: "POST", headers: { "Content-Type": "application/json", "X-LakeHunt-Demo-Role": demoRole() }, body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name: "explain_drift", arguments: { group: id } } }) }).then((r) => r.json());
      const res = JSON.parse(x.result.content[0].text);
      d.innerHTML = `<h2>${esc(id)}</h2><p class="reason"><b>${esc(res.summary)}</b> (${num(res.sampleRows)} recent rows checked)</p>
        ${res.unmatchedTemplates.length ? `<h3>Message shapes no template matches</h3><div class="tbl-wrap"><table><tr><th>Shape</th><th class="num">Lines</th><th>Example</th><th>Decide</th></tr>${res.unmatchedTemplates.map((t) => `<tr><td class="mono">${esc(t.template)}</td><td class="num">${num(t.lines)}</td><td class="small mono">${esc(t.example)}</td><td><div class="choices"><a class="choice" href="#/onboard/${enc(table)}/fields"><b>It carries entities</b><span>Add a template in field review</span></a><button class="choice" data-noise="${esc(t.suggestedMatch)}" ${can("analyst") ? "" : "disabled"}><b>It is noise</b><span>Heartbeats, keepalives: exclude lines containing <code>${esc(t.suggestedMatch)}</code></span></button></div></td></tr>`).join("")}</table></div>` : ""}
        ${res.missingColumns.length ? `<p>${st("fail", "missing columns")} ${res.missingColumns.map(esc).join(", ")}</p>` : ""}
        ${res.nearlyEmptyFields.length ? `<p>${st("review", "mostly empty")} ${res.nearlyEmptyFields.map((f) => `${esc(f.field)} (${pct(f.fill)})`).join(", ")}</p>` : ""}
        <h3 style="margin-top:14px">Daily extraction</h3>${barChart(r.filter((x) => x.extraction !== null).map((x) => ({ label: x.day, value: x.extraction, status: x.extraction >= 0.9 ? "ok" : "review", note: `${num(x.raw)} raw rows` })), { threshold: 0.9 })}`;
      $$("[data-noise]", d).forEach((b) => (b.onclick = async () => {
        if (!confirm(`Exclude lines containing "${b.dataset.noise}" from ${id}? This creates a registry change for approval.`)) return;
        try { const x = await api(`/registry/${enc(id)}/exclude`, { method: "POST", body: { text: b.dataset.noise } }); toast(`Approval #${x.approval} requested`); await refreshPending(); renderNav("coverage"); }
        catch (e) { toast(e.message, true); }
      }));
    } catch (e) { d.innerHTML = `<h2>${esc(id)}</h2><div class="callout warn">${esc(e.message)}</div>`; }
  };
  $$("[data-drift]").forEach((b) => (b.onclick = () => { explain(b.dataset.drift); $("#drift").scrollIntoView({ behavior: "smooth" }); }));
  if (gid) explain(gid);
};

// ------------------------------------------------------------------ API and agents
ROUTES.api = async (main) => {
  const base = location.origin;
  const tools = await fetch("/mcp", { method: "POST", headers: { "Content-Type": "application/json", "X-LakeHunt-Demo-Role": demoRole() }, body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/list" }) }).then((r) => r.json()).then((j) => j.result.tools).catch(() => []);
  main.innerHTML = `${pageHeader("API and agents", "Every screen is built on the REST API; agents connect through the MCP endpoint and cannot approve changes.")}
    <div class="grid g2"><div class="card"><h2>REST API</h2><dl class="kv"><dt>Base URL</dt><dd class="mono">${esc(base)}/api/v1</dd><dt>Reference</dt><dd><a href="/api/docs" target="_blank">OpenAPI (Swagger UI)</a> · <a href="/api/openapi.json" target="_blank">openapi.json</a></dd><dt>Sign-in</dt><dd>Entra ID bearer token for the app registration; roles LakeHunt.Admin, .Analyst, .Viewer</dd></dl>
      <h3 style="margin-top:14px">Example: hunt a value</h3><pre>curl -H "Authorization: Bearer $TOKEN" \\
  "${esc(base)}/api/v1/hunt/value?v=203.0.113.45&days=7"</pre>
      <h3 style="margin-top:14px">Example: request a connector deployment</h3><pre>curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \\
  -d '{"solutions":[{"name":"Okta Single Sign-On"}],"tables":[{"name":"OktaV2_CL","plan":"Lake","retentionDays":365}]}' \\
  ${esc(base)}/api/v1/deployments</pre></div>
    <div class="card"><h2>MCP server for agents</h2><dl class="kv"><dt>Endpoint</dt><dd class="mono">${esc(base)}/mcp</dd><dt>Transport</dt><dd>Streamable HTTP (JSON responses)</dd><dt>Auth</dt><dd>Same Entra ID token as the API</dd></dl>
      <h3 style="margin-top:14px">Client configuration</h3><pre>{
  "mcpServers": {
    "lakehunt": {
      "type": "http",
      "url": "${esc(base)}/mcp",
      "headers": { "Authorization": "Bearer &lt;token&gt;" }
    }
  }
}</pre>
      <div class="callout blue" style="margin-top:12px">The same hunt queries also ship as KQL in the deployment bundle (mcp/tools.yaml) for saving as custom tools in the Microsoft Sentinel MCP server.</div></div></div>
    <div class="card" style="margin-top:16px"><h2>MCP tools available to your role (${tools.length})</h2><div class="tbl-wrap"><table><tr><th>Tool</th><th>What it does</th><th>Parameters</th></tr>${tools.map((t) => `<tr><td class="mono"><b>${esc(t.name)}</b></td><td>${esc(t.description)}</td><td class="small mono">${Object.keys(t.inputSchema.properties || {}).map(esc).join(", ")}</td></tr>`).join("")}</table></div></div>
    <div class="card" style="margin-top:16px"><h2>Where agents help, and where people decide</h2><div class="tbl-wrap"><table><tr><th>Agent task</th><th>Tools</th><th>Checked by</th></tr>
      <tr><td>Draft a mapping for a new table</td><td class="mono">propose_mapping, preview_mapping, save_draft_mapping</td><td>Generator and regex checks, preview coverage, then Admin approval</td></tr>
      <tr><td>Explain a coverage drop</td><td class="mono">explain_drift</td><td>Deterministic: unmatched shapes and empty columns from recent rows</td></tr>
      <tr><td>Run post-onboarding checks</td><td class="mono">validate_source</td><td>Three checks automatic; the hand check needs a person</td></tr>
      <tr><td>Plan a connector</td><td class="mono">plan_connector</td><td>Content catalog; deployment needs Admin approval</td></tr>
      <tr><td>Hunt</td><td class="mono">hunt_value, auth_events, timeline, related, pivot_raw</td><td>Fixed, parameterised queries over the index</td></tr></table></div></div>`;
};

// ------------------------------------------------------------------ settings and audit
ROUTES.admin = async (main) => {
  const [s, audit] = await Promise.all([api("/settings"), can("admin") ? api("/audit?limit=100") : Promise.resolve([])]);
  main.innerHTML = `${pageHeader("Settings and audit", "Settings come from the container's environment variables; change them there and restart the revision.")}
    <div class="grid g2"><div class="card"><h2>Settings</h2><dl class="kv">${Object.entries(s).filter(([k]) => k !== "liveMissing").map(([k, v]) => `<dt>${esc(k)}</dt><dd class="mono">${esc(v === "" ? "(not set)" : v)}</dd>`).join("")}</dl>
      ${s.liveMissing.length && s.mode === "live" ? `<div class="callout warn">Missing for live mode: ${s.liveMissing.map(esc).join(", ")}</div>` : ""}</div>
    <div class="card"><h2>Roles</h2><div class="tbl-wrap"><table><tr><th>App role</th><th>Can</th></tr><tr><td class="mono">LakeHunt.Viewer</td><td>Dashboards, coverage, hunting</td></tr><tr><td class="mono">LakeHunt.Analyst</td><td>Viewer, plus field review, drafts, validation, deployment requests, raw search</td></tr><tr><td class="mono">LakeHunt.Admin</td><td>Analyst, plus approving registry and workspace changes, retiring entries, audit log</td></tr></table></div></div></div>
    <div class="card" style="margin-top:16px"><h2>Audit log</h2>${can("admin") ? `<div class="tbl-wrap"><table><tr><th>When</th><th>Who</th><th>Action</th><th>Detail</th></tr>${audit.map((a) => `<tr><td>${when(a.at)}</td><td>${esc(a.by)}</td><td class="mono">${esc(a.action)}</td><td class="small mono">${esc(a.detail).slice(0, 200)}</td></tr>`).join("")}</table></div>` : `<div class="empty">Admins only</div>`}</div>`;
};
