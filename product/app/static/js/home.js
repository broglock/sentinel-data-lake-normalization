/* Home: the three jobs and one list of what needs a person. */
import { ROUTES, $, api, esc, enc, can, pageHeader, st, navToken } from "./core.js";
import { nextStep, stepHref } from "./onboard.js";
import { rejectedByTable } from "./fields.js";

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

ROUTES.home = async (main) => {
  const tok = navToken();
  const [t, aps] = await Promise.all([
    can("analyst") ? api("/tables") : Promise.resolve({ tables: [] }),
    can("analyst") ? api("/approvals") : Promise.resolve([]),
  ]);
  if (tok !== navToken()) return;
  const pend = can("admin") ? aps.filter((a) => a.status === "pending") : [];
  const rej = rejectedByTable(aps);
  const todo = t.tables.map((x) => ({ t: x, n: nextStep(x, rej[x.name]) })).filter((x) => x.n.attention);
  const review = todo.filter((x) => x.n.step === "fields").length;
  const rows = [
    ...pend.map((a) => `<div class="att"><div><b>#${a.id} ${esc(a.title)}</b><div class="small muted">Requested by ${esc(a.requested_by)}; waiting for an Admin</div></div><a class="btn sm primary" href="#/approve">Review</a></div>`),
    ...todo.map(({ t: x, n }) => `<div class="att"><div><b>${esc(x.name)}</b> ${st(x.status)}<div class="small muted">${esc(n.why)}</div></div><a class="btn sm" href="${stepHref(x, n)}">${esc(n.label)}</a></div>`),
  ];
  main.innerHTML = pageHeader("What do you want to do?") + `
    <div class="tasks">
      <div class="task"><h2>Hunt</h2><p class="muted">Search one IP, user, host, URL or hash across every source.</p>
        <form class="hero-search" id="hhome"><input type="search" id="hq" aria-label="Value to hunt" placeholder="One IP, user, host, URL or hash"><button class="btn primary">Hunt</button></form></div>
      ${can("analyst") ? `<a class="task" href="#/onboard"><h2>Onboard a source</h2><p class="muted">Decide what each field holds, preview it, submit it.</p><span class="task-n">${review ? `${plural(review, "source")} ${review === 1 ? "needs" : "need"} review` : "Nothing waiting"}</span></a>` : ""}
      ${can("admin") ? `<a class="task" href="#/approve"><h2>Review and approve</h2><p class="muted">Changes wait here before they reach the tenant.</p><span class="task-n">${pend.length ? `${plural(pend.length, "change")} waiting` : "Nothing waiting"}</span></a>` : ""}
    </div>
    ${can("analyst") ? `<section class="card section"><h2>Needs attention <span class="count">${rows.length}</span></h2>${rows.join("") || `<div class="empty">Nothing needs you right now.</div>`}</section>` : ""}`;
  $("#hhome").onsubmit = (e) => { e.preventDefault(); const v = $("#hq").value.trim(); if (v) location.hash = "#/hunt/" + enc(v); };
};
