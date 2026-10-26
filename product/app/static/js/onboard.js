/* Onboard: one flow per source. Steps: pick → fields → preview → submit → deploy → validate. */
import { ROUTES, ALIAS, $, $$, api, esc, enc, pct, when, can, ME, st, modal, toast, pageHeader, disclose, navToken } from "./core.js";
import { renderFields, renderPreview, rejectedByTable, rejectReason } from "./fields.js";

// The next action for a table, from its onboarding stage and coverage status.
// `rejected` is the table's latest registry approval when an Admin rejected it (see rejectedByTable).
export function nextStep(t, rejected = null) {
  const live = (t.groups || []).find((g) => g.status === "live");
  const pending = (t.groups || []).some((g) => g.status === "pending");
  if (rejected && ["detected", "proposed", "in_review", "failed"].includes(t.stage)) {
    return { step: "fields", label: "Fix and resubmit", attention: true, why: `Rejected by ${rejected.decided_by}: ${rejectReason(rejected)}` };
  }
  switch (t.stage) {
    case "detected":
    case "proposed":
      return { step: "fields", label: "Review fields", attention: true,
        why: t.status === "classifier-only" ? "Searchable by value only; fields not reviewed" : "New table; fields not reviewed" };
    case "in_review": return { step: "fields", label: "Continue review", why: "Field review in progress", attention: true };
    case "failed": return { step: "fields", label: "Back to review", why: "Validation found a problem", attention: true };
    case "registry":   // live mode stays here after approval until someone creates the jobs
      return live && !pending ? { step: "deploy", label: "Deploy", why: "Approved; jobs to create", attention: true }
        : { step: "submit", label: "View request", why: "Waiting for an Admin", attention: false };
    case "deployed": return { step: "deploy", label: "Deploy", why: "Approved; jobs to create", attention: true };
    case "validating": return { step: "validate", label: "Finish validation", why: "A check needs a person", attention: true };
    default:
      if (t.status === "review" && live) {
        return { step: "coverage", href: `#/coverage/${enc(live.id)}`, label: "Explain drop", attention: true,
          why: `Extraction ${pct(t.extraction)}, below the 90% target` };
      }
      return { step: "fields", label: "View mapping", why: "Live", attention: false };
  }
}

export const stepHref = (t, n) => n.href || `#/onboard/${enc(t.name)}/${n.step}`;

export const STEPS = [["pick", "Pick source"], ["fields", "Decide fields"], ["preview", "Preview"], ["submit", "Submit"], ["deploy", "Deploy"], ["validate", "Validate"]];
// "approved" is not a server stage: it is "registry" with a live mapping and nothing pending (live mode, jobs not created yet).
const STAGE_STEP = { detected: "fields", proposed: "fields", in_review: "fields", failed: "fields", registry: "submit", approved: "deploy", deployed: "deploy", validating: "validate", live: "validate" };
// Renderers per step: (main, table, headHtml, stage) => Promise. Tasks 5 and 7 add preview, submit, deploy, validate.
export const STEP_VIEWS = {
  fields: (main, table, head) => renderFields(main, table, head),
  preview: (main, table, head) => renderPreview(main, table, head),
  submit: (main, table, head, stage) => renderSubmit(main, table, head, stage),
  deploy: (main, table, head, stage) => renderDeploy(main, table, head, stage),
  validate: (main, table, head, stage) => renderValidate(main, table, head, stage),
};

export function stepper(table, current, stage) {
  const reached = STEPS.findIndex(([k]) => k === (STAGE_STEP[stage] || "fields"));
  return `<ol class="stepper">${STEPS.map(([k, label], i) => {
    const cls = k === current ? "now" : (i < reached || stage === "live") ? "done" : "";
    const reachable = k === "pick" || i <= Math.max(reached, 2);
    const inner = `<b>${i + 1}</b>${esc(label)}`;
    return `<li class="step ${cls}">${reachable ? `<a href="${k === "pick" ? "#/onboard" : `#/onboard/${enc(table)}/${k}`}">${inner}</a>` : `<span>${inner}</span>`}</li>`;
  }).join("")}</ol>`;
}

async function stageOf(table) {
  const o = await api(`/onboarding/${enc(table)}`);
  if (o.stage) return o.stage.stage;
  const live = await api("/registry?status=live");
  return live.some((r) => r.group.table === table) ? "live" : "detected";
}

async function landing(main) {
  const tok = navToken();
  const [r, aps] = await Promise.all([api("/tables"), api("/approvals")]);
  if (tok !== navToken()) return;
  const rej = rejectedByTable(aps);
  const row = (t) => { const n = nextStep(t, rej[t.name]); return `<div class="att"><div><b>${esc(t.name)}</b> ${st(t.status)}<div class="small muted">${esc(n.why)}</div></div><a class="btn sm ${n.attention ? "primary" : ""}" href="${stepHref(t, n)}">${esc(n.label)}</a></div>`; };
  const groups = [
    ["Needs a decision", (t) => ["detected", "proposed", "in_review", "failed"].includes(t.stage)],
    ["Waiting for approval", (t) => t.stage === "registry" && nextStep(t).step === "submit"],
    ["Deploy and validate", (t) => ["deployed", "validating"].includes(t.stage) || (t.stage === "registry" && nextStep(t).step === "deploy")],
  ];
  const live = r.tables.filter((t) => t.stage === "live");
  main.innerHTML = pageHeader("Onboard a source", "Map a source's fields, get it approved, deployed and validated.", `<a class="btn" href="#/catalog">Plan a new connector</a>`) +
    groups.map(([h, f]) => { const ts = r.tables.filter(f); return ts.length ? `<section class="card section"><h2>${h} <span class="count">${ts.length}</span></h2>${ts.map(row).join("")}</section>` : ""; }).join("") +
    disclose(`Live sources (${live.length})`, live.map(row).join(""));
}

ROUTES.onboard = async (main, arg) => {
  if (!arg) return landing(main);
  if (arg.startsWith("~group/")) {            // old #/validation/<group> links: a group id is not always "<table>:…" (CEF:Fortinet/Fortigate)
    const gid = arg.slice("~group/".length);
    const g = (await api("/registry")).find((r) => r.id === gid);
    location.replace(g ? `#/onboard/${enc(g.group.table)}/validate` : "#/onboard");
    return;
  }
  const tok = navToken();
  const [table, want] = arg.split("/");
  let stage = await stageOf(table);
  if (stage === "registry") {
    const gs = (await api("/registry")).filter((r) => r.group.table === table);
    if (gs.some((r) => r.status === "live") && !gs.some((r) => r.status === "pending")) stage = "approved";
  }
  if (tok !== navToken()) return;
  const step = STEP_VIEWS[want] ? want : (STAGE_STEP[stage] in STEP_VIEWS ? STAGE_STEP[stage] : "fields");
  const head = pageHeader(table, `Stage: ${esc(stage.replace(/_/g, " "))}`) + stepper(table, step, stage);
  await STEP_VIEWS[step](main, table, head, stage);
};

ALIAS.sources = () => "onboard";
ALIAS.review = (arg) => (arg ? `onboard/${enc(arg)}/fields` : "onboard");

async function renderSubmit(main, table, head, stage) {
  const tok = navToken();
  const aps = await api("/approvals");
  if (tok !== navToken()) return;
  const a = aps.find((x) => x.status === "pending" && x.kind === "registry" && x.payload.group.table === table);
  const rej = rejectedByTable(aps)[table];
  main.innerHTML = head + `<div class="card section">${a
    ? `<h2>Waiting for an Admin</h2><p>Approval <b>#${a.id}</b> was requested by ${esc(a.requested_by)} at ${when(a.requested_at)}. Nothing is live until an Admin approves it.</p>${can("admin") ? `<a class="btn primary" href="#/approve">Review it now</a>` : ""}`
    : ["approved", "deployed", "validating", "live"].includes(stage)
      ? `<h2>Approved</h2><p>The mapping is live. Next, deploy and validate it.</p><a class="btn primary" href="#/onboard/${enc(table)}/deploy">Next: Deploy</a>`
      : rej
        ? `<h2>Rejected</h2><p>${esc(rej.decided_by)} rejected approval #${rej.id} at ${when(rej.decided_at)}: <b>${esc(rejectReason(rej))}</b></p><a class="btn primary" href="#/onboard/${enc(table)}/fields">Change the fields</a>`
        : `<h2>Nothing submitted yet</h2><p>Decide the fields and check the preview, then submit from the preview step.</p><a class="btn primary" href="#/onboard/${enc(table)}/preview">Go to preview</a>`}</div>`;
}

async function renderDeploy(main, table, head, stage) {
  const tok = navToken();
  const [b, reg] = await Promise.all([api("/build"), api("/registry?status=live")]);
  if (tok !== navToken()) return;
  const mine = reg.filter((r) => r.group.table === table).map((r) => r.id);
  const jobs = b.jobs.filter((j) => mine.includes(j.group));
  const nb = b.notebookGroups.filter((g) => mine.includes(g));
  const ready = ["deployed", "validating", "live"].includes(stage);
  main.innerHTML = head + `<div class="card section">${!mine.length
    ? `<h2>Not approved yet</h2><p>This source has no live mapping. Submit it for approval first.</p>`
    : `<h2>What runs for this source</h2>
      ${jobs.length ? `<div class="tbl-wrap"><table><tr><th>KQL job to create</th><th>Output table</th><th></th></tr>${jobs.map((j) => `<tr><td class="mono">${esc(j.name)}</td><td class="mono">${esc(j.output)}</td><td><button class="btn sm" data-file="${esc(j.file)}">View query</button></td></tr>`).join("")}</table></div>` : ""}
      ${nb.length ? `<p><b>${nb.map(esc).join(", ")}</b> ${nb.length > 1 ? "are" : "is"} indexed by the hourly notebook. There is no KQL job to create.</p>` : ""}
      ${disclose("Portal steps", `<pre style="white-space:pre-wrap;max-height:none">${esc(b.files["DEPLOY.md"])}</pre>`)}
      <div class="row section"><a class="btn" href="/api/v1/build/bundle.zip">Download bundle</a>${ME.mode === "demo" ? `<button class="btn" id="runidx">Re-run index now</button>` : ""}
        ${ready ? `<a class="btn primary right" id="next" href="#/onboard/${enc(table)}/validate">Next: Validate</a>`
          : `<button class="btn primary right" id="markdep" ${can("analyst") ? "" : "disabled"}>I've created the jobs: mark deployed</button>`}</div>`}</div>`;
  $$("[data-file]", main).forEach((x) => (x.onclick = () => modal(x.dataset.file, `<pre style="max-height:70vh">${esc(b.files[x.dataset.file])}</pre>`)));
  if ($("#runidx")) $("#runidx").onclick = async () => { const r = await api("/index/run", { method: "POST" }); toast(r.message || `Indexed ${r.entityRows} entity rows from ${r.groups} groups`); };
  if ($("#markdep")) $("#markdep").onclick = async () => {
    try { await api(`/onboarding/${enc(table)}/stage`, { method: "POST", body: { stage: "deployed", note: "jobs created in the portal" } }); location.hash = `#/onboard/${enc(table)}/validate`; }
    catch (e) { toast(e.message, true); }
  };
}

const verdict = (r) => r.passed ? st("ok", "all four passed") : r.checks.some((c) => c.passed === false) ? st("fail", "back to review") : st("pending", "waiting on you");

function checksHtml(r) {
  return `<ol class="checks">${r.checks.map((c) => `<li class="check"><div class="head"><b>${esc(c.label)}</b>${c.passed === true ? st("ok", "pass") : c.passed === false ? st("fail", "fail") : st("pending", "needs you")}</div>
    <div class="small muted">${esc(c.detail)}</div>
    ${c.check === "hand" && c.passed !== true && Array.isArray(c.data) ? `${c.data.slice(0, 3).map((p) => `<div class="pair"><div><div class="small muted">Raw</div><pre>${esc(JSON.stringify(p.raw[0] || {}, null, 1))}</pre></div><div><div class="small muted">Index</div><pre>${esc(p.index.map((e) => `${e.EntityType}:${e.Role} = ${e.Value}${e.EventResult ? "  " + e.EventResult : ""}`).join("\n"))}</pre></div></div>`).join("")}
      <div class="row"><button class="btn sm primary" data-hc="yes">The rows match</button><button class="btn sm danger" data-hc="no">Something is wrong</button></div>` : ""}
    ${c.check === "canary" && c.data && c.data.needsOperator ? `<div class="row"><input type="text" data-cv placeholder="Test value you generated, e.g. 192.0.2.250"><button class="btn sm" data-cvgo>Check</button></div>` : ""}
  </li>`).join("")}</ol>`;
}

async function renderValidate(main, table, head, stage) {
  const tok = navToken();
  const reg = (await api("/registry?status=live")).filter((r) => r.group.table === table);
  if (tok !== navToken()) return;
  // Run the checks on their own only while onboarding; for a live source a run that needs a person would demote it.
  const auto = ["deployed", "validating"].includes(stage);
  if (!reg.length) { main.innerHTML = head + `<div class="card section"><h2>Not live yet</h2><p>Validation runs once the mapping is approved and deployed.</p></div>`; return; }
  main.innerHTML = head + reg.map((r, i) => `<section class="card section vgroup" data-gid="${esc(r.id)}" id="vg${i}"><h2>${esc(r.id)}</h2><div class="loader">Running the four checks…</div></section>`).join("");
  const show = (box, gid, r, body) => {
    box.innerHTML = `<div class="row"><h2>${esc(gid)} ${verdict(r)}</h2><button class="btn sm right" data-rerun>Run checks again</button></div>
      ${r.run_at ? `<p class="small muted">Last run ${when(r.run_at)}</p>` : ""}${checksHtml(r)}
      ${r.passed ? `<div class="callout section">Live: ${esc(table)} is searchable with roles. <a href="#/hunt">Hunt it</a></div>` : ""}`;
    $$("[data-hc]", box).forEach((b) => (b.onclick = () => run(box, gid, { ...body, handCheck: b.dataset.hc === "yes" })));
    const cv = $("[data-cvgo]", box);
    if (cv) cv.onclick = () => run(box, gid, { ...body, canaryValue: $("[data-cv]", box).value });
    $("[data-rerun]", box).onclick = () => run(box, gid, {});
  };
  const run = async (box, gid, body) => {
    box.innerHTML = `<h2>${esc(gid)}</h2><div class="loader">Running the four checks…</div>`;
    try { show(box, gid, await api(`/validation/${enc(gid)}/run`, { method: "POST", body }), body); }
    catch (e) { box.innerHTML = `<h2>${esc(gid)}</h2><div class="callout warn">${esc(e.message)}</div>`; }
  };
  const idle = (box, gid, last) => {
    box.innerHTML = `<div class="row"><h2>${esc(gid)} ${last ? verdict(last) : ""}</h2><button class="btn sm right" data-rerun>Run checks</button></div>
      <p class="small muted">${last ? `The last run (${when(last.run_at)}) did not pass all four checks.` : "No checks have run for this group yet."} Running them asks a person to compare sample rows.</p>`;
    $("[data-rerun]", box).onclick = () => run(box, gid, {});
  };
  const boxes = reg.map((r, i) => $(`#vg${i}`));
  await Promise.all(reg.map(async (r, i) => {
    const last = (await api(`/validation?group=${enc(r.id)}`))[0];
    if (tok !== navToken()) return;
    if (last && last.passed) show(boxes[i], r.id, last, {});
    else if (auto) await run(boxes[i], r.id, {});
    else idle(boxes[i], r.id, last);
  }));
}

ALIAS.validation = (arg) => (arg ? `onboard/~group/${enc(arg)}` : "onboard");
