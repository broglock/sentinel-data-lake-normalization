/* Approve: an inbox of pending changes. Each card says in plain words what the change does. */
import { ROUTES, ALIAS, $, $$, api, esc, pct, num, when, enc, ME, st, toast, modal, pageHeader, disclose, jsyaml, refreshPending, router } from "./core.js";

const ROLE_WORDS = {
  "user:Actor": "who did it", "user:Target": "the account signing in", "user:Src": "the user behind the traffic",
  "ip:Src": "source IP", "ip:Dst": "destination IP", "ip:Dvc": "reporting device IP",
  "host:Dvc": "reporting device", "host:Src": "source machine", "host:Dst": "destination machine",
};
const roleWords = (k) => { const [e, r] = k.split(":"); return ROLE_WORDS[k] || (r === "Unknown" ? `${e}, no role claimed` : `${e} (${r})`); };

function staticBullets(a, budget) {
  if (a.kind === "registry") {
    const g = a.payload.group, out = [];
    (g.exclude_text || []).forEach((t) => out.push(`Lines containing <code>${esc(t)}</code> are marked as noise and left out of the index.`));
    out.push(g.engine === "kql_job" ? `Indexed by KQL jobs (${num(budget.kqlJobs)} of ${num(budget.limit)} jobs in use now).` : "Indexed by the hourly notebook; no KQL job is added.");
    return out;
  }
  return [
    ...(a.payload.solutions || []).map((s) => `Install the <b>${esc(s.name)}</b> solution from the Content hub.`),
    ...(a.payload.tables || []).map((t) => `Create table <b>${esc(t.name)}</b> on the ${esc(t.plan === "Auxiliary" ? "Lake" : t.plan)} plan, kept ${num(t.retentionDays)} days.`),
  ];
}

function card(a, budget) {
  return `<section class="card section approval" data-aid="${a.id}">
    <div class="row"><h2>#${a.id} ${esc(a.title)}</h2><span class="muted small right">requested by ${esc(a.requested_by)} at ${when(a.requested_at)}</span></div>
    <h3>What this changes</h3>
    <ul class="changes" id="ch-${a.id}">${a.kind === "registry" ? `<li class="muted" data-pvli>Checking what the index will hold…</li>` : ""}${staticBullets(a, budget).map((x) => `<li>${x}</li>`).join("")}</ul>
    ${disclose("Show request details", a.kind === "registry" ? `<pre>${esc(jsyaml(a.payload.group))}</pre>` : `<pre>${esc(JSON.stringify(a.payload, null, 2))}</pre>`)}
    <div class="row section"><button class="btn primary" data-ok="${a.id}">Approve</button><button class="btn danger" data-no="${a.id}">Reject</button>
      <span class="row" id="rj-${a.id}" hidden><input type="text" id="rjr-${a.id}" aria-label="Reason for rejecting" placeholder="Reason, sent back to the requester" style="min-width:320px"><button class="btn danger" data-noconfirm="${a.id}">Confirm reject</button></span></div>
  </section>`;
}

async function fillPreview(a) {
  const li = $(`#ch-${a.id} [data-pvli]`);
  if (!li) return;
  try {
    const g = a.payload.group;
    const r = await api(`/tables/${enc(g.table)}/preview`, { method: "POST", body: { group: g } });
    if (r.errors && r.errors.length) { li.outerHTML = `<li>${st("review", "check")} ${r.errors.map(esc).join("; ")}</li>`; return; }
    const ents = Object.entries(r.byEntity).map(([k, n]) => `${esc(roleWords(k))} (${num(n)})`).join(", ");
    const c = r.coverage;
    li.outerHTML = `<li><b>${esc(g.table)}</b> becomes searchable with roles: ${ents || "none"}.</li>
      <li>On ${num(c.RawRows)} sample rows, ${pct(c.ExtractionRate)} have an entity (target 90%)${c.TemplateMatchRate === null ? "" : ` and ${pct(c.TemplateMatchRate)} match a template (target 70%)`}.</li>`;
  } catch (e) { li.textContent = "Preview unavailable: " + e.message; }
}

ROUTES.approve = async (main) => {
  const [rows, b] = await Promise.all([api("/approvals"), api("/build")]);
  const pend = rows.filter((r) => r.status === "pending"), done = rows.filter((r) => r.status !== "pending");
  main.innerHTML = pageHeader("Review and approve", ME.mode === "demo"
    ? "Nothing reaches the tenant until you approve it. In demo mode, approving simulates the Azure calls."
    : "Nothing reaches the tenant until you approve it. Approving runs the change with the app's managed identity.") +
    (pend.length ? pend.map((a) => card(a, b.budget)).join("") : `<div class="card"><div class="empty">Nothing is waiting for approval.</div></div>`) +
    disclose(`History (${done.length})`, `<div class="tbl-wrap"><table><tr><th>#</th><th>Change</th><th>Status</th><th>Requested</th><th>Decided</th><th></th></tr>${done.map((a) => `<tr><td>${a.id}</td><td>${esc(a.title)}</td><td>${st(a.status)}</td><td>${esc(a.requested_by)}<div class="small muted">${when(a.requested_at)}</div></td><td>${esc(a.decided_by || "")}<div class="small muted">${when(a.decided_at)}</div></td><td>${a.result ? `<button class="btn sm" data-res="${a.id}">Result</button>` : ""}</td></tr>`).join("")}</table></div>`);
  const byId = Object.fromEntries(rows.map((r) => [String(r.id), r]));
  $$("[data-res]").forEach((x) => (x.onclick = () => modal("Result", `<pre>${esc(JSON.stringify(byId[x.dataset.res].result, null, 2))}</pre>`)));
  $$("[data-ok]").forEach((x) => (x.onclick = async () => {
    x.disabled = true;
    try { await api(`/approvals/${x.dataset.ok}/approve`, { method: "POST" }); toast(`Approved #${x.dataset.ok}`); }
    catch (e) { toast(e.message, true); }
    await refreshPending(); router();
  }));
  $$("[data-no]").forEach((x) => (x.onclick = () => { $(`#rj-${x.dataset.no}`).hidden = false; $(`#rjr-${x.dataset.no}`).focus(); }));
  $$("[data-noconfirm]").forEach((x) => (x.onclick = async () => {
    const id = x.dataset.noconfirm, reason = $(`#rjr-${id}`).value.trim();
    if (!reason) { toast("Give a reason, so the requester knows what to change.", true); return; }
    try { await api(`/approvals/${id}/reject`, { method: "POST", body: { reason } }); toast(`Rejected #${id}`); }
    catch (e) { toast(e.message, true); }
    await refreshPending(); router();
  }));
  pend.filter((a) => a.kind === "registry").forEach(fillPreview);
};

ALIAS.approvals = () => "approve";
