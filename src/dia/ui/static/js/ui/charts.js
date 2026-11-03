import { html } from "../html.js";

export function Meter({ label, used, limit, unit }) {
  const pct = limit ? Math.min(100, (100 * used) / limit) : 0;
  return html`<div class="meter"><div class="row" style="justify-content:space-between">
      <span class="muted">${label}</span><span>${Math.round(used)}${limit ? ` / ${limit}` : ""} ${unit}</span></div>
    <div class="meter-track"><span class=${`meter-fill ${pct >= 100 ? "over" : ""}`} style=${`width:${pct}%`}></span></div></div>`;
}

export function Bars({ rows, value, label, title }) {
  const max = Math.max(1, ...rows.map(value));
  return html`<div class="hbars">${rows.map((r) => html`
    <div class="hbar" title=${title(r)}>
      <span class="hbar-label">${label(r)}</span>
      <span class="hbar-track"><span class="hbar-fill" style=${`width:${(100 * value(r)) / max}%`}></span></span>
      <span class="hbar-value">${value(r)}</span>
    </div>`)}</div>`;
}

export function Columns({ rows, days }) {
  // One column per day of the period, empty days included, so gaps are visible.
  const byDay = Object.fromEntries(rows.map((r) => [r.day, r]));
  const list = [];
  for (let i = days - 1; i >= 0; i--) {
    const day = new Date(Date.now() - i * 86400000).toISOString().slice(0, 10);
    list.push(byDay[day] || { day, calls: 0, minutes: 0 });
  }
  const max = Math.max(1, ...list.map((r) => r.calls));
  return html`<div class="cols">${list.map((r) => html`
    <div class="col" title=${`${r.day}: ${r.calls} · ${r.minutes} min`}>
      <span class="col-fill" style=${`height:${(100 * r.calls) / max}%`}></span></div>`)}</div>
    <div class="cols-axis faint"><span>${list[0].day.slice(5)}</span><span>${list[list.length - 1].day.slice(5)}</span></div>`;
}
