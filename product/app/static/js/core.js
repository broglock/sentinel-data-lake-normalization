/* LevelBlue Lake Hunt web UI: shared helpers, router and navigation. Plain ES modules, no build step. */
// ------------------------------------------------------------------ helpers
export const $ = (s, el = document) => el.querySelector(s);
export const $$ = (s, el = document) => [...el.querySelectorAll(s)];
export const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export const pct = (v, d = 0) => (v === null || v === undefined ? "–" : (v * 100).toFixed(d) + "%");
export const num = (v) => (v === null || v === undefined ? "–" : Number(v).toLocaleString());
export const when = (t) => { if (!t) return "–"; const d = new Date(t); return isNaN(d) ? esc(t) : d.toISOString().slice(0, 16).replace("T", " ") + "Z"; };
export const enc = encodeURIComponent;
export const ME = { role: "viewer" };
const LEVEL = { none: 0, viewer: 1, analyst: 2, admin: 3 };
export const can = (r) => LEVEL[ME.role] >= LEVEL[r];

export function demoRole() { try { return localStorage.getItem("lh.role") || "admin"; } catch { return "admin"; } }

export async function api(path, opts = {}) {
  const headers = { "Content-Type": "application/json", "X-LakeHunt-Demo-Role": demoRole() };
  const r = await fetch("/api/v1" + path, { ...opts, headers: { ...headers, ...(opts.headers || {}) },
    body: opts.body && typeof opts.body !== "string" ? JSON.stringify(opts.body) : opts.body });
  if (!r.ok) {
    let msg = r.statusText;
    try { const j = await r.json(); msg = j.detail || msg; } catch { /* keep */ }
    throw new Error(`${r.status}: ${msg}`);
  }
  const ct = r.headers.get("content-type") || "";
  return ct.includes("json") ? r.json() : r.text();
}

export function toast(msg, err = false) {
  const t = document.createElement("div");
  t.className = "toast" + (err ? " err" : "");
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), err ? 7000 : 3500);
}

export const st = (s, label) => `<span class="st ${esc(s)}">${esc(label || String(s).replace(/[-_]/g, " "))}</span>`;
export const tier = (t) => t === 1 ? `<span class="tier t1" title="Tier 1: mapped with roles">1</span>` : t === 2 ? `<span class="tier t2" title="Tier 2: classifier only, no roles">2</span>` : `<span class="tier t0" title="Not indexed">–</span>`;
export const layerTag = (l) => `<span class="tag ${l === "asim" ? "asim" : ""}">${esc({ asim: "ASIM logic", registry: "Registry rules", template: "Templates", classifier: "Classifier" }[l] || l)}</span>`;

// tooltip on [data-tip]
const tipEl = () => $("#tip");
document.addEventListener("mousemove", (e) => {
  const t = e.target.closest("[data-tip]");
  const tip = tipEl();
  if (!t) { tip.style.display = "none"; return; }
  tip.innerHTML = t.getAttribute("data-tip");
  tip.style.display = "block";
  const x = Math.min(e.clientX + 14, window.innerWidth - tip.offsetWidth - 10);
  tip.style.left = x + "px"; tip.style.top = (e.clientY + 14) + "px";
});

export function modal(title, html, wide = true) {
  const m = document.createElement("div");
  m.style.cssText = "position:fixed;inset:0;background:rgba(5,5,47,.55);z-index:40;display:flex;align-items:flex-start;justify-content:center;padding:40px 16px;overflow:auto";
  m.innerHTML = `<div class="card" style="width:${wide ? "min(1100px,100%)" : "min(620px,100%)"}"><div class="row"><h2 style="margin:0">${esc(title)}</h2><button class="btn ghost right" data-close>Close ✕</button></div><hr>${html}</div>`;
  m.addEventListener("click", (e) => { if (e.target === m || e.target.closest("[data-close]")) m.remove(); });
  document.body.appendChild(m);
  return m;
}

export function jsyaml(o, ind = "") {
  if (Array.isArray(o)) return o.map((v) => (typeof v === "object" && v !== null ? `${ind}- ${jsyaml(v, ind + "  ").trimStart()}` : `${ind}- ${JSON.stringify(v)}`)).join("\n");
  if (typeof o === "object" && o !== null) return Object.entries(o).map(([k, v]) => (typeof v === "object" && v !== null ? (Object.keys(v).length ? `${ind}${k}:\n${jsyaml(v, ind + "  ")}` : `${ind}${k}: ${Array.isArray(v) ? "[]" : "{}"}`) : `${ind}${k}: ${typeof v === "string" ? JSON.stringify(v) : v}`)).join("\n");
  return String(o);
}

// ------------------------------------------------------------------ page parts
export const pageHeader = (title, sub = "", actions = "") =>
  `<div class="ph"><div class="ph-text"><h1>${esc(title)}</h1>${sub ? `<p class="sub">${sub}</p>` : ""}</div>${actions ? `<div class="ph-actions">${actions}</div>` : ""}</div>`;
export const disclose = (summary, html, open = false) =>
  `<details class="more"${open ? " open" : ""}><summary>${esc(summary)}</summary><div class="more-body">${html}</div></details>`;

// ------------------------------------------------------------------ navigation
const ICON = {
  home: '<path d="M2 9h5V2H2zm7 5h5V2H9zM2 14h5v-3H2z" fill="currentColor"/>',
  hunt: '<circle cx="7" cy="7" r="4.5" stroke="currentColor" fill="none" stroke-width="1.8"/><path d="M10.5 10.5L14 14" stroke="currentColor" stroke-width="2"/>',
  onboard: '<circle cx="8" cy="4" r="2.5" fill="currentColor"/><path d="M3 14c0-3 2.2-5 5-5s5 2 5 5z" fill="currentColor"/>',
  approve: '<path d="M2 8l4 4 8-9" stroke="currentColor" fill="none" stroke-width="2"/>',
  coverage: '<path d="M2 14V8h3v6zm4.5 0V4h3v10zM11 14V1h3v13z" fill="currentColor"/>',
  registry: '<path d="M3 2h10v12H3zM5 5h6M5 8h6M5 11h4" stroke="currentColor" fill="none" stroke-width="1.4"/>',
  catalog: '<path d="M2 3h12v2H2zm0 4h12v2H2zm0 4h8v2H2z" fill="currentColor"/>',
  deploy: '<path d="M8 1l5 5h-3v5H6V6H3zM2 13h12v2H2z" fill="currentColor"/>',
  api: '<path d="M5 4L1 8l4 4M11 4l4 4-4 4" stroke="currentColor" fill="none" stroke-width="1.6"/>',
  admin: '<circle cx="8" cy="8" r="2.5" fill="currentColor"/><path d="M8 1v2.5M8 12.5V15M1 8h2.5M12.5 8H15M3 3l1.8 1.8M11.2 11.2L13 13M3 13l1.8-1.8M11.2 4.8L13 3" stroke="currentColor" stroke-width="1.5"/>',
  about: '<circle cx="8" cy="8" r="6.5" stroke="currentColor" fill="none" stroke-width="1.4"/><path d="M8 7v4.5M8 4.5v.5" stroke="currentColor" stroke-width="1.8"/>',
};
export const NAV = [["home", "Home", "viewer"], ["hunt", "Hunt", "viewer"], ["onboard", "Onboard", "analyst"], ["approve", "Approve", "admin"]];
export const MORE_NAV = [
  ["coverage", "Coverage", "viewer", "Extraction rate per source, drift, and why a source drops."],
  ["registry", "Registry", "viewer", "Every mapping, its versions, and YAML export for Git."],
  ["catalog", "Connectors", "viewer", "The Content hub catalog: plan a connector's tables and tier."],
  ["deploy", "Build and deploy", "viewer", "All KQL jobs, notebook settings and the deployment bundle."],
  ["api", "API and agents", "viewer", "The REST API, the MCP endpoint and what agents may do."],
  ["admin", "Settings and audit", "admin", "Environment settings, roles and the audit log."],
  ["about", "About", "viewer", "Why an index: ASIM coverage across the content catalog."],
];
const ROUTE_ROLE = { more: "viewer", ...Object.fromEntries([...NAV, ...MORE_NAV].map(([k, , r]) => [k, r])) };
let pendingCount = 0;

export function renderNav(active) {
  const link = ([k, label]) => `<a href="#/${k}" data-nav="${k}" class="${active === k ? "on" : ""}"><svg viewBox="0 0 16 16">${ICON[k] || ""}</svg>${label}${k === "approve" && pendingCount ? `<span class="n">${pendingCount}</span>` : ""}</a>`;
  const visible = (items) => items.filter(([, , r]) => can(r));
  const moreOpen = active === "more" || MORE_NAV.some(([k]) => k === active);
  $("#nav").innerHTML = visible(NAV).map(link).join("") +
    `<details class="nav-more"${moreOpen ? " open" : ""}><summary>More</summary>${visible(MORE_NAV).map(link).join("")}</details>`;
}

export async function refreshPending() {
  try { pendingCount = can("admin") ? (await api("/approvals?status=pending")).length : 0; } catch { pendingCount = 0; }
}

export const ROUTES = {};
// Old links keep working: each old page key maps to its new hash (without "#/"). Later modules add entries.
export const ALIAS = { overview: () => "home" };

// Each navigation gets a number and a fresh view element. A slow screen from an earlier navigation writes into its
// own detached view, and checks navToken() after an await before touching anything found by id.
let navSeq = 0;
export const navToken = () => navSeq;

export async function router() {
  const seq = ++navSeq;
  const hash = location.hash.replace(/^#\/?/, "") || "home";
  const [page, ...rest] = hash.split("/");
  const arg = rest.length ? decodeURIComponent(rest.join("/")) : null;
  if (ALIAS[page]) { location.replace("#/" + ALIAS[page](arg)); return; }
  const route = ROUTES[page] ? page : "home";
  renderNav(route);
  $("#nav").classList.remove("open");
  const main = $("#main");
  const need = ROUTE_ROLE[page] || ROUTE_ROLE[route];   // guard by the requested page, even before its module exists
  if (need && !can(need)) {
    main.innerHTML = pageHeader("Not available") +
      `<div class="card"><p>This screen needs the ${esc(need)} role. You are signed in as ${esc(ME.role)}.</p><a class="btn" href="#/home">Go to Home</a></div>`;
    return;
  }
  const view = document.createElement("div");
  view.innerHTML = `<div class="loader">Loading…</div>`;
  main.replaceChildren(view);
  try {
    await ROUTES[route](view, arg);
  } catch (e) {
    if (seq === navSeq) view.innerHTML = `<div class="card"><h2>Something went wrong</h2><p class="muted">${esc(e.message)}</p></div>`;
  }
  if (seq === navSeq) window.scrollTo(0, 0);
}

// ------------------------------------------------------------------ start
export async function start() {
  try { const t = localStorage.getItem("lh.theme") || ""; if (t) document.documentElement.dataset.theme = t; $("#theme").value = t; } catch { /* no storage */ }
  $("#theme").onchange = (e) => { const v = e.target.value; if (v) document.documentElement.dataset.theme = v; else delete document.documentElement.dataset.theme; try { localStorage.setItem("lh.theme", v); } catch { /* ignore */ } };
  const me = await api("/me");
  Object.assign(ME, me);
  $("#mode").textContent = me.mode;
  $("#who").textContent = `${me.name} · ${me.role}`;
  $("#ws").textContent = "· " + me.workspace;
  if (me.mode === "demo") {
    const sel = $("#demoRole"); sel.style.display = ""; sel.value = demoRole();
    sel.onchange = () => { try { localStorage.setItem("lh.role", sel.value); } catch { /* ignore */ } location.reload(); };
  }
  await refreshPending();
  window.addEventListener("hashchange", router);
  router();
}
