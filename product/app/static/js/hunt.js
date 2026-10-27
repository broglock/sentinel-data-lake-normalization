/* Hunt: one value across every indexed source. */
import { ROUTES, $, $$, api, esc, num, when, enc, ME, st, tier, modal, pageHeader } from "./core.js";
import { timelineChart } from "./charts.js";

export const splitValues = (text) => [...new Set(String(text).split(/[,;\n]+/).map((x) => x.trim()).filter(Boolean))];

const EXAMPLES = [["203.0.113.45", "suspicious IP"], ["CONTOSO\\jsmith", "user, Windows format"], ["jsmith@contoso.com", "user, UPN"],
  ["198.51.100.7", "outbound destination"], ["WS-0412", "workstation"]];
const result = (r) => st(r === "Success" ? "ok" : r === "Failure" ? "fail" : "info", r || "–");
const rawBtn = (p) => `<button class="btn sm" data-pv='${esc(JSON.stringify(p))}'>Raw</button>`;

ROUTES.hunt = async (main, q) => {
  main.innerHTML = pageHeader("Hunt", "One value across every indexed source, back to the original log line.") + `
    <div class="card"><div class="hero-search"><input type="search" id="hv" aria-label="Value to hunt" placeholder="One IP, user (any format), host, URL or hash" value="${esc(q || "")}">
      <select id="hd" aria-label="Period"><option value="1">24 hours</option><option value="3">3 days</option><option value="7" selected>7 days</option><option value="30">30 days</option></select>
      <button class="btn primary" id="hgo">Hunt</button></div>
      ${ME.mode === "demo" ? `<div class="row small" style="margin-top:10px"><span class="muted">Try:</span>${EXAMPLES.map(([v, l]) => `<button class="btn sm ghost" data-ex="${esc(v)}" title="${esc(l)}">${esc(v)}</button>`).join("")}</div>` : ""}</div>
    <div id="hres" class="section"></div>`;
  const out = $("#hres");

  const go = async (text) => {
    const vals = splitValues(text);
    if (!vals.length) return;
    if (vals.length > 1) {
      out.innerHTML = `<div class="card" id="hpick"><h2>Hunt one value at a time</h2><p class="muted">Pick the value to search first.</p>
        <div class="row">${vals.map((v) => `<button class="btn" data-pick="${esc(v)}">${esc(v)}</button>`).join("")}</div></div>`;
      $$("[data-pick]", out).forEach((b) => (b.onclick = () => { $("#hv").value = b.dataset.pick; go(b.dataset.pick); }));
      return;
    }
    const v = vals[0];
    history.replaceState(null, "", "#/hunt/" + enc(v));
    const days = $("#hd").value;
    out.innerHTML = `<div class="loader">Searching the index…</div>`;
    try {
      const [r, auth, net] = await Promise.all([api(`/hunt/value?v=${enc(v)}&days=${days}`), api(`/hunt/auth?user=${enc(v)}&days=${days}`), api(`/hunt/network?ip=${enc(v)}&days=${days}`)]);
      const srcs = r.sources;
      if (!srcs.length) {
        out.innerHTML = `<div class="card" id="hnone"><div class="empty">Not found in the index for this period. Try a longer period, or check <a href="#/coverage">Coverage</a> for sources that are searchable by value only.</div></div>`;
        return;
      }
      const events = srcs.reduce((a, s) => a + s.Events, 0);
      const sumBy = (res) => r.timeline.filter((t) => t.EventResult === res).reduce((a, t) => a + (t.Count || 1), 0);
      const fails = sumBy("Failure"), succ = sumBy("Success");
      const short = v.toLowerCase().split("\\").pop().split("@")[0];
      const tabs = [
        ["where", "Where it appears", srcs.length, () => `<div class="tbl-wrap"><table><tr><th>Source</th><th>As</th><th>Roles</th><th>Results</th><th class="num">Events</th><th>Tier</th></tr>${srcs.map((s) => `<tr><td><b>${esc(s.SourceGroup)}</b><div class="small muted">${when(s.FirstSeen)} to ${when(s.LastSeen)}</div></td><td>${esc(s.EntityType)}</td><td>${s.Roles.map((x) => `<span class="tag">${esc(x)}</span>`).join("")}</td><td>${s.Results.map(result).join(" ")}</td><td class="num">${num(s.Events)}</td><td>${s.Tiers.map(tier).join("")}</td></tr>`).join("")}</table></div>`],
        ["events", "Activity by hour", r.timeline.length, () => `<p class="small muted">One row per hour, source, role and result. Raw opens up to three sample events behind the row.</p><div class="tbl-wrap"><table><tr><th>First seen</th><th>Source</th><th>Event</th><th>Matched as</th><th class="num">Events</th><th>Other entities</th><th></th></tr>${r.timeline.slice(0, 200).map((t) => `<tr><td>${when(t.EventStartTime)}</td><td>${esc(t.SourceGroup)}</td><td>${esc(t.EventType || "–")} ${t.EventResult ? result(t.EventResult) : ""}</td><td><span class="tag">${esc(t.MatchedAs)}</span></td><td class="num">${num(t.Count || 1)}</td><td class="small">${t.Entities.filter((e) => !e.toLowerCase().includes(short)).slice(0, 4).map(esc).join("<br>")}</td><td>${rawBtn({ table: t.SourceTable, time: t.EventStartTime, until: t.LastSeen || t.EventStartTime, value: t.Value || v, key: (t.SampleKeys || [t.SourceRecordKey]).join(","), group: t.SourceGroup })}</td></tr>`).join("")}</table></div>`],
        ["auth", "Sign-ins", auth.length, () => `<div class="tbl-wrap"><table><tr><th>Time</th><th>Source</th><th>Result</th><th>User as logged</th><th>From IP</th><th></th></tr>${auth.slice(0, 50).map((a) => `<tr><td>${when(a.EventStartTime)}</td><td>${esc(a.SourceGroup)}</td><td>${result(a.EventResult)}</td><td class="mono">${esc(a.User)}</td><td>${a.SrcIpAddr ? `<a href="#/hunt/${enc(a.SrcIpAddr)}">${esc(a.SrcIpAddr)}</a>` : "–"}</td><td>${rawBtn({ table: a.SourceTable, time: a.EventStartTime, value: a.User, key: a.SourceRecordKey, group: a.SourceGroup })}</td></tr>`).join("")}</table></div>`],
        ["net", "Network sessions", net.length, () => `<div class="tbl-wrap"><table><tr><th>Source</th><th>From</th><th>To</th><th class="num">Port</th><th>Action</th><th class="num">Sessions</th></tr>${net.map((n) => `<tr><td>${esc(n.SourceGroup)}</td><td>${esc(n.SrcIpAddr)}</td><td>${esc(n.DstIpAddr)}</td><td class="num">${esc(n.DstPortNumber ?? "")}</td><td>${n.Actions.map(esc).join(", ")}</td><td class="num">${n.Sessions}</td></tr>`).join("")}</table></div>`],
        ["related", "Seen with it", r.related.length, () => `<p class="small muted">Entities in the same sampled events. Pick one to hunt it next.</p><div class="tbl-wrap"><table><tr><th>Entity</th><th>Roles</th><th class="num">Sources</th><th class="num">Events</th></tr>${r.related.map((x) => `<tr class="click" data-hunt="${esc(x.Value)}"><td><span class="tag">${esc(x.EntityType)}</span> <b>${esc(x.Value)}</b></td><td>${x.Roles.map(esc).join(", ")}</td><td class="num">${x.Sources.length}</td><td class="num">${x.Events}</td></tr>`).join("")}</table></div>`],
      ].filter(([k, , n]) => k === "where" || n > 0);
      out.innerHTML = `<p class="summary" id="hsum">Seen in <b>${srcs.length}</b> source${srcs.length === 1 ? "" : "s"} · <b>${num(events)}</b> event${events === 1 ? "" : "s"} · <b>${fails}</b> failure${fails === 1 ? "" : "s"}, <b>${succ}</b> success${succ === 1 ? "" : "es"}</p>
        <div class="card"><h2>Timeline</h2>${timelineChart(r.timeline)}</div>
        <div class="card section"><div class="tabs" id="htabs">${tabs.map(([k, l, n], i) => `<button data-tab="${k}" class="${i ? "" : "on"}">${l} <span class="count">${n}</span></button>`).join("")}</div><div id="htab"></div></div>`;
      const show = (k) => {
        $$("#htabs [data-tab]").forEach((b) => b.classList.toggle("on", b.dataset.tab === k));
        $("#htab").innerHTML = tabs.find(([x]) => x === k)[3]();
        $$("[data-hunt]", $("#htab")).forEach((x) => (x.onclick = () => { $("#hv").value = x.dataset.hunt; go(x.dataset.hunt); }));
        $$("[data-pv]", $("#htab")).forEach((x) => (x.onclick = async () => {
          const p = JSON.parse(x.dataset.pv);
          const rows = await api(`/hunt/pivot?table=${enc(p.table)}&time=${enc(p.time)}&until=${enc(p.until || p.time)}&value=${enc(p.value)}&key=${enc(p.key)}&group=${enc(p.group)}`);
          modal(`Original ${rows.length === 1 ? "row" : "rows"} in ${p.table}`, `<div class="modal-raw">${rows.length ? rows.map((row) => `<pre>${esc(JSON.stringify(row, null, 2))}</pre>`).join("<br>") : `<div class="empty">No raw row found</div>`}</div>`);
        }));
      };
      $$("#htabs [data-tab]").forEach((b) => (b.onclick = () => show(b.dataset.tab)));
      show("where");
    } catch (e) { out.innerHTML = `<div class="callout warn">${esc(e.message)}</div>`; }
  };

  $("#hgo").onclick = () => go($("#hv").value);
  $("#hv").addEventListener("keydown", (e) => { if (e.key === "Enter") go($("#hv").value); });
  $$("[data-ex]").forEach((b) => (b.onclick = () => { $("#hv").value = b.dataset.ex; go(b.dataset.ex); }));
  if (q) go(q);
};
