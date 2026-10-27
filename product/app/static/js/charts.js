import { esc, pct, when } from "./core.js";

// ------------------------------------------------------------------ charts (inline SVG)
// Horizontal bars with a threshold line; status carried by icon + label, not colour alone.
export function barChart(items, { threshold = null, max = 1, fmt = (v) => pct(v), width = 640 } = {}) {
  if (!items.length) return `<div class="empty">No data yet</div>`;
  const rowH = 26, labelW = 200, right = 70, top = 8;
  const h = top + items.length * rowH + 22;
  const plotW = width - labelW - right;
  const x = (v) => labelW + Math.max(0, Math.min(1, v / max)) * plotW;
  let s = `<svg viewBox="0 0 ${width} ${h}" role="img" aria-label="bar chart">`;
  [0, 0.25, 0.5, 0.75, 1].forEach((t) => {
    s += `<line x1="${x(t * max)}" x2="${x(t * max)}" y1="${top}" y2="${h - 18}" stroke="var(--chart-grid)"/>`;
    s += `<text x="${x(t * max)}" y="${h - 4}" text-anchor="middle">${fmt(t * max)}</text>`;
  });
  items.forEach((it, i) => {
    const y = top + i * rowH;
    const w = Math.max(2, x(it.value) - labelW);
    // Tooltip HTML is rendered with innerHTML: escape every value inside it, then escape the whole for the attribute.
    const tipText = esc(`<b>${esc(it.label)}</b><br>${esc(fmt(it.value))}${it.note ? "<br>" + esc(it.note) : ""}`);
    s += `<g data-tip="${tipText}" ${it.href ? `style="cursor:pointer" onclick="location.hash='${it.href}'"` : ""}>`;
    s += `<rect x="0" y="${y}" width="${width}" height="${rowH}" fill="transparent"/>`;
    s += `<text x="${labelW - 8}" y="${y + rowH / 2 + 4}" text-anchor="end">${esc(it.label.length > 30 ? it.label.slice(0, 29) + "…" : it.label)}</text>`;
    s += `<rect x="${labelW}" y="${y + 6}" width="${w}" height="${rowH - 12}" rx="4" fill="${it.muted ? "var(--pale)" : "var(--chart-bar)"}"/>`;
    const icon = it.status === "ok" ? "✓" : it.status === "review" ? "!" : it.status === "classifier-only" ? "●" : "";
    s += `<text x="${x(it.value) + 6}" y="${y + rowH / 2 + 4}" style="font-weight:700">${fmt(it.value)} ${icon}</text>`;
    s += `</g>`;
  });
  if (threshold !== null) {
    s += `<line x1="${x(threshold)}" x2="${x(threshold)}" y1="${top - 4}" y2="${h - 18}" stroke="var(--crit)" stroke-dasharray="4 3" stroke-width="1.5"/>`;
    s += `<text x="${x(threshold) - 4}" y="${top + 2}" text-anchor="end" style="fill:var(--crit-ink);font-weight:700">target ${fmt(threshold)}</text>`;
  }
  return `<div class="chart">${s}</svg></div>`;
}

export function spark(values, { width = 120, height = 28, min = 0, max = 1 } = {}) {
  const pts = values.map((v, i) => (v === null || v === undefined ? null : [4 + (i * (width - 8)) / Math.max(1, values.length - 1), height - 4 - ((v - min) / (max - min || 1)) * (height - 8)]));
  let d = "", started = false;
  pts.forEach((p) => { if (!p) { started = false; return; } d += (started ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1); started = true; });
  const last = [...pts].reverse().find(Boolean);
  return `<svg viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" aria-hidden="true"><path d="${d}" fill="none" stroke="var(--chart-bar)" stroke-width="2" stroke-linejoin="round"/>${last ? `<circle cx="${last[0]}" cy="${last[1]}" r="3" fill="var(--chart-bar)"/>` : ""}</svg>`;
}

// One lane per source; marks: filled circle = success, cross = failure, ring = no result.
export function timelineChart(rows, width = 900) {
  if (!rows.length) return `<div class="empty">Nothing in the index for this value</div>`;
  const lanes = [...new Set(rows.map((r) => r.SourceGroup))];
  const labelW = 210, right = 20, top = 26, laneH = 26;
  const h = top + lanes.length * laneH + 26;
  const ts = rows.map((r) => Date.parse(r.EventStartTime));
  let lo = Math.min(...ts), hi = Math.max(...ts);
  if (hi - lo < 60000) { lo -= 300000; hi += 300000; }
  const pad = (hi - lo) * 0.03; lo -= pad; hi += pad;
  const X = (t) => labelW + ((t - lo) / (hi - lo)) * (width - labelW - right);
  let s = `<svg viewBox="0 0 ${width} ${h}" role="img" aria-label="timeline">`;
  for (let i = 0; i <= 4; i++) {
    const t = lo + ((hi - lo) * i) / 4;
    s += `<line x1="${X(t)}" x2="${X(t)}" y1="${top - 6}" y2="${h - 20}" stroke="var(--chart-grid)"/>`;
    s += `<text x="${X(t)}" y="${h - 6}" text-anchor="middle">${new Date(t).toISOString().slice(5, 16).replace("T", " ")}</text>`;
  }
  lanes.forEach((l, i) => {
    const y = top + i * laneH + laneH / 2;
    s += `<line x1="${labelW}" x2="${width - right}" y1="${y}" y2="${y}" stroke="var(--chart-grid)"/>`;
    s += `<text x="${labelW - 8}" y="${y + 4}" text-anchor="end">${esc(l.length > 30 ? l.slice(0, 29) + "…" : l)}</text>`;
  });
  rows.forEach((r) => {
    const y = top + lanes.indexOf(r.SourceGroup) * laneH + laneH / 2;
    const x = X(Date.parse(r.EventStartTime));
    // Log values are untrusted: escape each inside the tooltip HTML (rendered with innerHTML), then the whole for the attribute.
    const tip = esc(`<b>${esc(r.SourceGroup)}</b><br>${when(r.EventStartTime)}<br>${esc(r.EventType || "event")} · ${esc(r.EventResult || "no result")}${r.Count > 1 ? ` · ${r.Count} events` : ""}<br>matched as ${esc(r.MatchedAs)}<br>${(r.Entities || []).slice(0, 6).map(esc).join("<br>")}`);
    let mark;
    if (r.EventResult === "Failure") mark = `<path d="M${x - 5} ${y - 5}L${x + 5} ${y + 5}M${x + 5} ${y - 5}L${x - 5} ${y + 5}" stroke="var(--crit)" stroke-width="2.5" stroke-linecap="round"/>`;
    else if (r.EventResult === "Success") mark = `<circle cx="${x}" cy="${y}" r="5.5" fill="var(--good)" stroke="var(--surface)" stroke-width="2"/>`;
    else mark = `<circle cx="${x}" cy="${y}" r="5" fill="var(--surface)" stroke="var(--chart-bar)" stroke-width="2"/>`;
    s += `<g data-tip="${tip}"><circle cx="${x}" cy="${y}" r="10" fill="transparent"/>${mark}</g>`;
  });
  s += `</svg>`;
  return `<div class="legend"><span><svg width="12" height="12"><circle cx="6" cy="6" r="5" fill="var(--good)"/></svg> Success</span><span><svg width="12" height="12"><path d="M2 2L10 10M10 2L2 10" stroke="var(--crit)" stroke-width="2.5"/></svg> Failure</span><span><svg width="12" height="12"><circle cx="6" cy="6" r="4.5" fill="none" stroke="var(--chart-bar)" stroke-width="2"/></svg> No result</span></div><div class="chart">${s}</div>`;
}
