/* Onboard step 2 (Decide fields): one row per field with the recommendation; Change opens the choices.
   Decisions are kept in memory per table so steps 2 and 3 share them. */
import { $, $$, api, esc, pct, num, enc, when, st, modal, toast, disclose, refreshPending, navToken } from "./core.js";
import { barChart } from "./charts.js";

export const EFFECT = {
  "ip:Src": "Hunters see it as the source IP; sign-in and network views use it as SrcIpAddr.",
  "ip:Dst": "Network views use it as the destination (DstIpAddr).",
  "ip:Dvc": "Recorded as the reporting device's address (DvcIpAddr).",
  "ip:Unknown": "Found by hunt_value, but no direction is claimed.",
  "user:Target": "Sign-in views list it as the account signing in (TargetUsername).",
  "user:Actor": "Audit views list it as who did it (ActorUsername).",
  "user:Src": "Network views list it as the user behind the traffic (SrcUsername).",
  "user:Unknown": "Found by hunt_value, but no role is claimed.",
  "host:Dvc": "Recorded as the device that wrote the log (DvcHostname).",
  "host:Src": "Recorded as the source machine (SrcHostname).",
  "host:Dst": "Recorded as the destination machine (DstHostname).",
};

const STATE = new Map();

// The latest registry approval per table, kept only when an Admin rejected it: { table: approval }.
export function rejectedByTable(approvals) {
  const latest = {};
  approvals.filter((a) => a.kind === "registry").forEach((a) => {
    const t = a.payload.group.table;
    if (!latest[t] || a.id > latest[t].id) latest[t] = a;
  });
  return Object.fromEntries(Object.entries(latest).filter(([, a]) => a.status === "rejected"));
}
export const rejectReason = (a) => (a.result && a.result.reason) || "no reason given";

function initDecisions(ctx) {
  const { P, S } = ctx;
  S.dec = {}; S.tpl = {}; S.open = {}; S.topen = {};
  P.cards.forEach((c) => {
    const rec = c.recommended || {};
    const base = { accepted: false, kind: c.kind, use: c.decision };
    if (c.decision === "entity") Object.assign(base, { entity: rec.entity, role: rec.role, asim: rec.asim });
    if (c.decision === "field") Object.assign(base, { asim: rec.asim });
    if (c.decision === "result") base.map = Object.fromEntries((c.values || []).map((v) => [v.value, v.suggested]));
    if (c.decision === "event_type") base.map = Object.fromEntries((c.values || []).map((v) => [v.value, ""]));
    if (c.decision === "skip") base.accepted = true;
    S.dec[c.field] = base;
  });
  (P.templates || []).forEach((t, i) => {
    S.tpl[i] = { include: t.share >= 0.02, outcome: t.outcomeSuggested || "", eventType: t.eventTypeSuggested || "", regex: t.suggestedRegex, match: t.suggestedMatch,
      slots: Object.fromEntries(t.slots.map((s) => [s.slot, { ...s.recommended, name: "" }])), accepted: false };
  });
}

export async function getState(table, preset = null) {
  if (!preset && STATE.has(table)) return STATE.get(table);
  const P = await api(`/tables/${enc(table)}/proposals${preset ? `?preset=${enc(preset)}` : ""}`);
  const prev = STATE.get(table);
  const ctx = { table, P, S: { meta: prev ? prev.S.meta : { id: `${table}:main`, vendor: "", product: "" } } };
  initDecisions(ctx);
  STATE.set(table, ctx);
  return ctx;
}

export function decisionsPayload({ P, S }) {
  const fields = [], d = { id: S.meta.id, preset: P.preset, vendor: S.meta.vendor, product: S.meta.product, fields, templates: [] };
  for (const [f, x] of Object.entries(S.dec)) {
    if (x.use === "entity" && x.entity) fields.push({ field: f, kind: x.kind, entity: x.entity, role: x.role || "Unknown", asim: x.asim || "" });
    if (x.use === "field" && x.asim) fields.push({ field: f, kind: x.kind, entity: "", role: "", asim: x.asim });
    if (x.use === "result") d.result = { field: f, kind: x.kind, map: x.map };
    if (x.use === "event_type") { const m = Object.fromEntries(Object.entries(x.map || {}).filter(([, v]) => v)); d.event_type = Object.keys(m).length ? { field: f, kind: x.kind, map: m, default: "Other" } : { field: f, kind: x.kind }; }
    if (x.use === "record_key") d.record_key = { field: f, kind: x.kind };
  }
  const tpls = P.templates || [];
  Object.entries(S.tpl).forEach(([i, t]) => {
    if (!t.include) return;
    let rx = t.regex; const slots = {}; const used = new Set();
    tpls[i].slots.forEach((s) => {
      const sl = t.slots[s.slot] || {};
      let name = sl.name || sl.asim || (sl.entity ? `${sl.entity}_${sl.role || "Unknown"}` : s.slot);
      name = name.replace(/\W/g, "") || s.slot; let n = name, k = 2; while (used.has(n)) n = name + k++; used.add(n);
      rx = rx.split(`(?P<${s.slot}>`).join(`(?P<${n}>`);
      slots[n] = sl.entity ? { entity: sl.entity, role: sl.role || "Unknown" } : {};
    });
    d.templates.push({ id: `tpl-${+i + 1}`, match: t.match, regex: rx, event_type: t.eventType, event_result: t.outcome, tier: 1, slots });
  });
  if (P.textColumn && (d.templates.length || P.kvSource)) d.text_column = P.textColumn;
  if (!d.event_type && !P.textColumn) delete d.event_type;
  return d;
}

export function counts({ S }) {
  const all = Object.values(S.dec).filter((x) => x.use !== "skip");
  const tpl = Object.values(S.tpl).filter((t) => t.include);
  return { done: all.filter((x) => x.accepted).length + tpl.filter((t) => t.accepted).length, total: all.length + tpl.length };
}

function summaryOf(x) {
  if (x.use === "skip") return "Skipped: stays in the raw table.";
  if (x.use === "entity") return `Indexed as <b>${esc(x.entity)}:${esc(x.role)}</b>${x.asim ? ` → ASIM <b>${esc(x.asim)}</b>` : ""}`;
  if (x.use === "result") return `Result: ${Object.entries(x.map).filter(([, o]) => o !== "Ignore").map(([v, o]) => `<code>${esc(v)}</code> → ${esc(o)}`).join(", ") || "no values mapped"}`;
  if (x.use === "event_type") return "Used as the event type";
  if (x.use === "record_key") return "Used as the unique ID for pivots";
  if (x.use === "field") return x.asim ? `Mapped to ASIM <b>${esc(x.asim)}</b>` : "Not mapped";
  return "";
}

const roleChoicesFor = (P, e) => P.roleChoices[e] || [{ value: "Unknown", label: "No role", help: "Searched by value" }];

function cardBody(P, cd, x) {
  const rec = cd.recommended || {};
  const f = esc(cd.field);
  if (cd.decision === "entity" || x.use === "entity") {
    const ents = P.entityChoices.map((e) => `<button class="choice ${x.entity === e.value && x.use !== "skip" ? "on" : ""} ${rec.entity === e.value ? "rec" : ""}" data-f="${f}" data-entity="${e.value}"><b>${esc(e.label)}</b></button>`).join("");
    const roles = x.entity ? roleChoicesFor(P, x.entity).map((r) => `<button class="choice ${x.role === r.value ? "on" : ""} ${rec.role === r.value && rec.entity === x.entity ? "rec" : ""}" data-f="${f}" data-role="${r.value}"><b>${esc(r.label)}</b><span>${esc(r.help)}</span></button>`).join("") : "";
    return `<div class="qlabel">What is in this field?</div><div class="choices">${ents}</div>
      ${x.entity ? `<div class="qlabel">What role does it play in the event?</div><div class="choices">${roles}</div>` : ""}
      <div class="effect">${x.entity ? `Indexed as <b>${esc(x.entity)}:${esc(x.role || "Unknown")}</b>${x.asim ? ` → ASIM <b>${esc(x.asim)}</b>` : ""}. ${esc(EFFECT[`${x.entity}:${x.role}`] || "Found by hunt_value.")}` : "Skipped: stays in the raw table, reachable through search_raw."}</div>
      <div class="row" style="margin-top:8px"><button class="btn sm primary" data-accept="${f}">Use this</button><button class="btn sm ghost" data-skip="${f}">Skip field</button></div>`;
  }
  if (cd.decision === "result") {
    return `<div class="qlabel">Which values mean success and which mean failure?</div><div class="vmap">${(cd.values || []).map((v) => {
      const cur = x.map[v.value] || "Ignore";
      return `<code>${esc(v.value || "(empty)")}</code><span class="small muted">${num(v.rows)} rows</span><span class="seg">${["Success", "Failure", "Ignore"].map((o) => `<button class="${o === "Success" ? "s" : o === "Failure" ? "f" : "i"} ${cur === o ? "on" : ""}" data-f="${f}" data-v="${esc(v.value)}" data-o="${o}">${o}</button>`).join("")}</span>`; }).join("")}</div>
      <div class="effect">Becomes EventResult. auth_events can then filter on Success or Failure.</div>
      <div class="row" style="margin-top:8px"><button class="btn sm primary" data-accept="${f}">Use as the result</button><button class="btn sm ghost" data-skip="${f}">Don't use</button></div>`;
  }
  if (cd.decision === "event_type") {
    return `<div class="qlabel">Name the activity for each value (leave blank to keep the value as is)</div><div class="vmap">${(cd.values || []).map((v) => `<code>${esc(v.value || "(empty)")}</code><span class="small muted">${num(v.rows)} rows</span><select data-f="${f}" data-etv="${esc(v.value)}"><option value="">(keep value)</option>${["Logon", "Logoff", "NetworkSession", "HTTPsession", "Other"].map((o) => `<option ${x.map[v.value] === o ? "selected" : ""}>${o}</option>`).join("")}</select>`).join("")}</div>
      <div class="row" style="margin-top:8px"><button class="btn sm primary" data-accept="${f}">Use as the event type</button><button class="btn sm ghost" data-skip="${f}">Don't use</button></div>`;
  }
  if (cd.decision === "record_key") {
    return `<div class="effect">Used to build SourceRecordKey so every index row points back to exactly one raw row.</div>
      <div class="row" style="margin-top:8px"><button class="btn sm primary" data-accept="${f}">Use as the unique ID</button><button class="btn sm ghost" data-skip="${f}">Don't use</button></div>`;
  }
  return `<div class="qlabel">Map to an ASIM field (not an entity)</div><select data-f="${f}" data-asim>${["", ...P.asimFields].map((a) => `<option ${x.asim === a ? "selected" : ""} value="${esc(a)}">${esc(a || "(don't map)")}</option>`).join("")}</select>
    <div class="row" style="margin-top:8px"><button class="btn sm primary" data-accept="${f}">Use this</button><button class="btn sm ghost" data-skip="${f}">Skip field</button></div>`;
}

function rowHtml(ctx, cd) {
  const { P, S } = ctx, x = S.dec[cd.field], f = esc(cd.field);
  const open = S.open[cd.field] && !x.accepted;
  return `<div class="frow ${x.accepted ? "accepted" : ""}" data-row="${f}">
    <div class="frow-line"><span class="fname">${f}</span><span class="conf ${esc(cd.confidence || "none")}">${esc(cd.confidence || "no")} confidence</span>
      <span class="frow-rec">${x.accepted ? summaryOf(x) : esc(cd.reason)}</span>
      <span class="frow-act">${x.accepted ? `${st("ok", "decided")}<button class="btn ghost sm" data-change="${f}">Change</button>` : `<button class="btn sm primary" data-accept="${f}">Accept</button><button class="btn sm" data-change="${f}">${open ? "Close" : "Change"}</button>`}</span></div>
    ${open ? `<div class="frow-body"><div class="samples">${(cd.samples || []).slice(0, 5).map((s) => `<code title="${esc(s)}">${esc(s)}</code>`).join("")}</div><div class="small muted">${pct(cd.fillRate)} filled</div>${cardBody(P, cd, x)}</div>` : ""}
  </div>`;
}

function tplRow(ctx, t, i) {
  const { P, S } = ctx, s = S.tpl[i], open = S.topen[i] && !s.accepted;
  const slotRows = t.slots.map((sl) => {
    const v = s.slots[sl.slot];
    return `<tr><td><code>${esc(sl.token)}</code></td>
      <td><select data-ti="${i}" data-slot="${sl.slot}" data-k="entity">${P.entityChoices.map((e) => `<option value="${e.value}" ${v.entity === e.value ? "selected" : ""}>${esc(e.label)}</option>`).join("")}</select></td>
      <td>${v.entity ? `<select data-ti="${i}" data-slot="${sl.slot}" data-k="role">${roleChoicesFor(P, v.entity).map((r) => `<option value="${r.value}" ${v.role === r.value ? "selected" : ""}>${esc(r.label)}</option>`).join("")}</select>` : `<span class="muted small">–</span>`}</td></tr>`;
  }).join("");
  return `<div class="frow ${s.accepted ? "accepted" : ""} ${s.include ? "" : "skipped"}" data-trow="${i}">
    <div class="frow-line"><label class="inline"><input type="checkbox" data-tinc="${i}" ${s.include ? "checked" : ""}> Include</label>
      <span class="frow-rec"><code>${esc(t.template.length > 90 ? t.template.slice(0, 89) + "…" : t.template)}</code> <span class="small muted">${pct(t.share, 1)} of lines${s.outcome ? ` · ${esc(s.outcome)}` : ""}</span></span>
      ${s.include ? `<span class="frow-act">${s.accepted ? `${st("ok", "decided")}<button class="btn ghost sm" data-tchange="${i}">Change</button>` : `<button class="btn sm primary" data-taccept="${i}">Accept</button><button class="btn sm" data-tchange="${i}">${open ? "Close" : "Change"}</button>`}</span>` : ""}</div>
    ${open && s.include ? `<div class="frow-body"><pre style="white-space:pre-wrap">${esc(t.template)}</pre><div class="small muted">Example: <code>${esc(t.example)}</code></div>
      <div class="qlabel">What outcome does this message mean?</div>
      <span class="seg">${[["Success", "s"], ["Failure", "f"], ["", "i"]].map(([o, k]) => `<button class="${k} ${s.outcome === o ? "on" : ""}" data-ti="${i}" data-out="${o}">${o || "No outcome"}</button>`).join("")}</span>
      ${t.outcomeSuggested ? `<span class="small muted">Suggested: ${esc(t.outcomeSuggested)} (wording of the message)</span>` : ""}
      ${t.slots.length ? `<div class="qlabel">What does each placeholder hold?</div><div class="tbl-wrap"><table><tr><th>Placeholder</th><th>Holds</th><th>Role</th></tr>${slotRows}</table></div>` : ""}
      ${disclose("Advanced: match text and regex", `<div class="grid g2"><label class="small">Match text<input type="text" data-ti="${i}" data-match value="${esc(s.match)}" style="width:100%"></label><label class="small">Regex<input type="text" data-ti="${i}" data-regex value="${esc(s.regex)}" style="width:100%;font-family:var(--mono)"></label></div>`)}
      <div class="row" style="margin-top:8px"><button class="btn sm primary" data-taccept="${i}">Use this template</button></div></div>` : ""}
  </div>`;
}

export async function renderFields(main, table, head) {
  const tok = navToken();
  const [ctx, aps] = await Promise.all([getState(table), api("/approvals")]);
  if (tok !== navToken()) return;
  const rej = rejectedByTable(aps)[table];
  const draw = () => {
    const { P, S } = ctx;
    const live = (P.existing || []).find((e) => e.status === "live");
    const cards = P.cards.filter((c) => c.decision !== "skip");
    const pending = cards.filter((c) => !S.dec[c.field].accepted);
    const high = pending.filter((c) => c.confidence === "high");
    const rest = pending.filter((c) => c.confidence !== "high");
    const done = cards.filter((c) => S.dec[c.field].accepted);
    const skipped = P.cards.filter((c) => c.decision === "skip");
    const tpls = P.templates || [];
    const c = counts(ctx);
    const preset = P.presets.find((p) => p.value === P.preset);
    main.innerHTML = head + `
      ${rej ? `<div class="callout warn">${esc(rej.decided_by)} rejected approval #${rej.id} at ${when(rej.decided_at)}: <b>${esc(rejectReason(rej))}</b>. Change the fields and submit again.</div>` : ""}
      ${live ? `<div class="callout blue">This table already has a live mapping (<a href="#/registry/${enc(live.id)}">${esc(live.id)}</a>, version ${live.version}). Saving here creates a new draft for approval.</div>` : ""}
      <div class="card section"><div class="row"><label class="inline"><b>Kind of source</b> <select id="preset">${P.presets.map((p) => `<option value="${esc(p.value)}" ${P.preset === p.value ? "selected" : ""}>${esc(p.label)}</option>`).join("")}</select></label>
        <span class="small muted">${esc(preset ? preset.hint : "")}</span></div></div>
      ${high.length ? `<section class="card section"><div class="row"><h2>High confidence <span class="count">${high.length}</span></h2><button class="btn lime right" id="acceptHigh">Accept all ${high.length} high-confidence</button></div>${high.map((cd) => rowHtml(ctx, cd)).join("")}</section>` : ""}
      ${rest.length ? `<section class="card section"><h2>Needs a decision <span class="count">${rest.length}</span></h2>${rest.map((cd) => rowHtml(ctx, cd)).join("")}</section>` : ""}
      ${!pending.length ? `<div class="card section"><p>${st("ok", "done")} Every field is decided. Check the preview next.</p></div>` : ""}
      ${tpls.length ? `<section class="card section"><h2>Message templates <span class="count">${tpls.length}</span></h2><p class="small muted">Common message shapes in ${esc(P.textColumn)}. Shapes under 2% of lines start excluded.</p>${tpls.map((t, i) => tplRow(ctx, t, i)).join("")}</section>` : ""}
      ${done.length ? disclose(`Decided (${done.length})`, done.map((cd) => rowHtml(ctx, cd)).join("")) : ""}
      ${skipped.length ? disclose(`${skipped.length} fields left in the raw table`, `<p class="small muted">No entity-like values. Include one to map it to an ASIM field.</p><div class="row">${skipped.map((s) => `<button class="btn sm" data-include="${esc(s.field)}">${esc(s.field)}</button>`).join("")}</div>`) : ""}
      ${P.asimParsers.length ? disclose(`Microsoft ASIM parsers for this table (${P.asimParsers.length})`, `<p class="small muted">${esc(P.pathHelp)}</p><div class="tbl-wrap"><table><tr><th>Parser</th><th>Schema</th><th>Product</th><th></th></tr>${P.asimParsers.slice(0, 8).map((p) => `<tr><td class="mono">${esc(p.builtIn || p.parser)}</td><td>${esc(p.schema)}</td><td>${esc(p.product)}</td><td><button class="btn sm" data-expand="${esc(p.parser)}">Expand to lake KQL</button></td></tr>`).join("")}</table></div>`) : ""}
      <div class="sticky-bar section"><span class="small"><b>${c.done}</b> of ${c.total} decided</span><div class="progress"><i style="width:${c.total ? (100 * c.done) / c.total : 100}%"></i></div>
        ${pending.length ? `<button class="btn ghost" id="acceptAll">Accept all recommendations</button>` : ""}
        <a class="btn primary" id="toPreview" href="#/onboard/${enc(table)}/preview">Next: Preview</a></div>`;
    bind();
  };

  const bind = () => {
    const { S } = ctx;
    const P = () => ctx.P;
    $("#preset").onchange = async (e) => { await getState(table, e.target.value); Object.assign(ctx, STATE.get(table)); STATE.set(table, ctx); draw(); };
    $$("[data-change]", main).forEach((b) => (b.onclick = () => { const f = b.dataset.change, x = S.dec[f], cd = P().cards.find((c) => c.field === f); if (x.accepted) { x.accepted = false; if (x.use === "skip") x.use = cd.decision; S.open[f] = true; } else S.open[f] = !S.open[f]; draw(); }));
    $$("[data-entity]", main).forEach((b) => (b.onclick = () => { const x = S.dec[b.dataset.f]; x.use = "entity"; x.entity = b.dataset.entity; const rc = roleChoicesFor(P(), x.entity); x.role = rc.some((r) => r.value === x.role) ? x.role : rc[0].value; x.asim = P().asimByEntityRole[`${x.entity}:${x.role}`] || ""; draw(); }));
    $$("[data-role]", main).forEach((b) => (b.onclick = () => { const x = S.dec[b.dataset.f]; x.role = b.dataset.role; x.asim = P().asimByEntityRole[`${x.entity}:${x.role}`] || ""; draw(); }));
    $$("[data-accept]", main).forEach((b) => (b.onclick = () => { const x = S.dec[b.dataset.accept]; if (x.use === "skip") x.use = "entity"; x.accepted = true; S.open[b.dataset.accept] = false; draw(); }));
    $$("[data-skip]", main).forEach((b) => (b.onclick = () => { const x = S.dec[b.dataset.skip]; x.use = "skip"; x.accepted = true; S.open[b.dataset.skip] = false; draw(); }));
    $$("[data-include]", main).forEach((b) => (b.onclick = () => { const f = b.dataset.include, cd = P().cards.find((c) => c.field === f); cd.decision = "field"; S.dec[f] = { accepted: false, kind: cd.kind, use: "field", asim: "" }; S.open[f] = true; draw(); }));
    $$("[data-o]", main).forEach((b) => (b.onclick = () => { S.dec[b.dataset.f].map[b.dataset.v] = b.dataset.o; draw(); }));
    $$("[data-etv]", main).forEach((s) => (s.onchange = () => { S.dec[s.dataset.f].map[s.dataset.etv] = s.value; }));
    $$("[data-asim]", main).forEach((s) => (s.onchange = () => { S.dec[s.dataset.f].asim = s.value; }));
    $$("[data-tinc]", main).forEach((c) => (c.onchange = () => { S.tpl[c.dataset.tinc].include = c.checked; draw(); }));
    $$("[data-tchange]", main).forEach((b) => (b.onclick = () => { const i = b.dataset.tchange; if (S.tpl[i].accepted) { S.tpl[i].accepted = false; S.topen[i] = true; } else S.topen[i] = !S.topen[i]; draw(); }));
    $$("[data-taccept]", main).forEach((b) => (b.onclick = () => { S.tpl[b.dataset.taccept].accepted = true; S.topen[b.dataset.taccept] = false; draw(); }));
    $$("[data-out]", main).forEach((b) => (b.onclick = () => { S.tpl[b.dataset.ti].outcome = b.dataset.out; draw(); }));
    $$("select[data-slot]", main).forEach((s) => (s.onchange = () => { const v = S.tpl[s.dataset.ti].slots[s.dataset.slot]; v[s.dataset.k] = s.value; if (s.dataset.k === "entity") v.role = roleChoicesFor(P(), s.value)[0].value; v.asim = P().asimByEntityRole[`${v.entity}:${v.role}`] || ""; draw(); }));
    $$("[data-match]", main).forEach((i) => (i.onchange = () => { S.tpl[i.dataset.ti].match = i.value; }));
    $$("[data-regex]", main).forEach((i) => (i.onchange = () => { S.tpl[i.dataset.ti].regex = i.value; }));
    $$("[data-expand]", main).forEach((b) => (b.onclick = async () => {
      b.disabled = true; b.textContent = "Expanding…";
      try {
        const r = await api("/asim/expand", { method: "POST", body: { parser: b.dataset.expand } });
        modal(`${r.parser} as lake KQL`, `<p>${r.lakeSafe ? st("ok", "lake-safe: no function calls left") : st("review", "function calls left: " + r.remainingCalls.join(", "))}</p><pre>${esc(r.query)}</pre>`);
      } catch (e) { toast(e.message, true); }
      b.disabled = false; b.textContent = "Expand to lake KQL";
    }));
    if ($("#acceptHigh")) $("#acceptHigh").onclick = () => { P().cards.forEach((c) => { if (c.confidence === "high" && S.dec[c.field].use !== "skip") S.dec[c.field].accepted = true; }); draw(); };
    if ($("#acceptAll")) $("#acceptAll").onclick = () => { P().cards.forEach((c) => (S.dec[c.field].accepted = true)); Object.values(S.tpl).forEach((t) => { if (t.include) t.accepted = true; }); draw(); };
  };
  draw();
}

export async function renderPreview(main, table, head) {
  const tok = navToken();
  const ctx = await getState(table);
  if (tok !== navToken()) return;
  const { S } = ctx;
  const c = counts(ctx);
  main.innerHTML = head + `
    ${c.done < c.total ? `<div class="callout warn">${c.total - c.done} of ${c.total} fields are not reviewed yet. They are submitted with the recommendation shown on the fields step. <a href="#/onboard/${enc(table)}/fields">Review them</a></div>` : ""}
    <div class="card section" id="pv"><div class="loader">Running the mapping on sample rows…</div></div>
    ${disclose("Name and details", `<div class="grid g3"><label>Group ID<br><input type="text" id="gid" value="${esc(S.meta.id)}" style="width:100%"></label>
      <label>Vendor<br><input type="text" id="vendor" value="${esc(S.meta.vendor)}" style="width:100%"></label>
      <label>Product<br><input type="text" id="product" value="${esc(S.meta.product)}" style="width:100%"></label></div>`)}
    <div class="sticky-bar section"><a class="btn" href="#/onboard/${enc(table)}/fields">Back to fields</a><span class="right"></span>
      <button class="btn" id="saveDraft">Save draft</button><button class="btn primary" id="submit">Submit for approval</button></div>`;
  const pv = $("#pv");
  try {
    const r = await api(`/tables/${enc(table)}/preview`, { method: "POST", body: { decisions: decisionsPayload(ctx) } });
    if (r.errors && r.errors.length) {
      pv.innerHTML = `<h2>The mapping has problems</h2><div class="callout warn">${r.errors.map(esc).join("<br>")}</div>`;
    } else {
      const cov = r.coverage;
      const okE = cov.ExtractionRate >= 0.9, okT = cov.TemplateMatchRate === null || cov.TemplateMatchRate >= 0.7;
      pv.innerHTML = `<h2>What the index will hold <span class="muted small" style="font-weight:400">on ${num(cov.RawRows)} sample rows</span></h2>
        <div class="grid g2"><div class="kpi"><span class="v">${pct(cov.ExtractionRate)}</span><span class="l">rows with an entity ${st(okE ? "ok" : "review", okE ? "meets 90%" : "below 90%")}</span></div>
          <div class="kpi"><span class="v">${cov.TemplateMatchRate === null ? "n/a" : pct(cov.TemplateMatchRate)}</span><span class="l">template match ${cov.TemplateMatchRate === null ? "" : st(okT ? "ok" : "review", okT ? "meets 70%" : "below 70%")}</span></div></div>
        <h3 class="section">Entities by type and role</h3>
        ${barChart(Object.entries(r.byEntity).slice(0, 8).map(([k, v]) => ({ label: k, value: v, status: "" })), { max: Math.max(...Object.values(r.byEntity), 1), fmt: (v) => num(Math.round(v)), width: 520 })}
        <div class="row small">${Object.entries(r.byResult).map(([k, v]) => `<span class="tag">${esc(k)}: ${num(v)}</span>`).join("")}</div>
        <h3 class="section">Sample rows</h3>
        ${r.pairs.slice(0, 3).map((p) => `<div class="pair"><div><div class="small muted">Raw row</div><pre>${esc(JSON.stringify(p.raw, null, 1))}</pre></div><div><div class="small muted">Index rows</div><pre>${esc(p.index.map((e) => `${e.EntityType}:${e.Role} = ${e.Value}${e.EventResult ? "  " + e.EventResult : ""}`).join("\n"))}</pre></div></div>`).join("") || `<div class="empty">No rows produced an entity yet</div>`}
        ${disclose("Show generated code", `<h3>Registry YAML</h3><pre>${esc(r.yaml)}</pre><h3 class="section">Lake KQL</h3><pre>${esc(r.kql)}</pre>`)}`;
    }
  } catch (e) { pv.innerHTML = `<div class="callout warn">${esc(e.message)}</div>`; }
  if (tok !== navToken()) return;
  const save = async (submit) => {
    S.meta.id = $("#gid").value.trim() || `${table}:main`; S.meta.vendor = $("#vendor").value; S.meta.product = $("#product").value;
    $$("#saveDraft, #submit").forEach((b) => (b.disabled = true));
    try {
      const r = await api(`/registry/from-decisions/${enc(table)}`, { method: "POST", body: { decisions: decisionsPayload(ctx), submit } });
      toast(submit ? `Submitted. Approval #${r.approval} is waiting for an Admin.` : "Draft saved");
      await refreshPending();
      location.hash = submit ? `#/onboard/${enc(table)}/submit` : `#/onboard/${enc(table)}/fields`;
    } catch (e) { toast(e.message, true); $$("#saveDraft, #submit").forEach((b) => (b.disabled = false)); }
  };
  $("#saveDraft").onclick = () => save(false);
  $("#submit").onclick = () => save(true);
}
