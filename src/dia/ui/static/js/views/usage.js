import { useEffect, useState } from "preact/hooks";
import { html } from "../html.js";
import { api } from "../api.js";
import { t } from "../i18n.js";
import { Bars, Columns } from "../ui/charts.js";
import { ResourceState, useResource } from "../ui/resource.js";

export const pct = (v) => (v == null ? "–" : `${Math.round(v * 100)}%`);

export function UsageView({ toast }) {
  const [days, setDays] = useState(30);
  const res = useResource(`/api/usage?days=${days}`);
  const data = res.data;
  const load = res.reload;
  const apply = async (s) => {
    try { toast((await api("/api/settings/apply-suggestion", { method: "POST", body: s })).message); load(); }
    catch (e) { toast(e.message, "error"); }
  };
  if (!data) return html`<${ResourceState} res=${res} />`;
  const calls = data.agents.reduce((n, a) => n + a.calls, 0);
  const ok = data.agents.reduce((n, a) => n + a.ok, 0);
  const minutes = data.agents.reduce((n, a) => n + a.minutes, 0);
  const limited = data.agents.reduce((n, a) => n + a.limited, 0);
  const tiles = [[t("calls"), calls], [t("agent_time"), `${Math.round(minutes)} min`],
    [t("success"), calls ? `${Math.round((100 * ok) / calls)}%` : "–"], [t("limits_hit"), limited]];
  return html`
    <div class="page wide usage">
      <div class="page-head">
        <h1>${t("usage")}</h1>
        <div class="row">
          ${[7, 30, 90].map((d) => html`<button class="btn ${days === d ? "primary" : ""}" onClick=${() => setDays(d)}>${t("last_days", { days: d })}</button>`)}
        </div>
      </div>
      <div class="tiles">${tiles.map(([k, v]) => html`<div class="card tile"><div class="label">${k}</div><div class="tile-value">${v}</div></div>`)}</div>
      ${calls ? html`
        <div class="usage-charts">
          <div>
            <div class="label section">${t("calls_per_agent")}</div>
            <div class="card" style="margin-top:8px"><${Bars} rows=${data.agents} value=${(a) => a.calls} label=${(a) => a.agent}
              title=${(a) => `${a.agent}: ${a.calls} · ${Math.round((100 * a.ok) / a.calls)}% ok · ${a.minutes} min · ${t("limits_hit")}: ${a.limited}`} /></div>
          </div>
          <div>
            <div class="label section">${t("calls_per_day")}</div>
            <div class="card" style="margin-top:8px"><${Columns} rows=${data.daily} days=${days} /></div>
          </div>
        </div>
        <div class="label section">${t("projects")}</div>
        <div class="card table-wrap" style="margin-top:8px"><table class="table">
          <tr><th>${t("project")}</th><th>${t("tasks")}</th><th>${t("col_done")}</th><th>${t("col_failed")}</th></tr>
          ${data.projects.map((p) => html`<tr><td>${p.project}</td><td>${p.tasks}</td><td>${p.done}</td><td>${p.failed}</td></tr>`)}
        </table></div>` : html`<p class="muted">${t("no_usage")}</p>`}
      ${data.suggestions?.length ? html`<div class="label section">${t("proposals")}</div>
        ${data.suggestions.map((s) => html`<div class="card row" style="margin-top:8px">
          <span style="flex:1">${t("proposal_text", { project: s.project, agent: s.agent, current: s.current })}<br /><span class="faint">${s.reason}</span></span>
          <button class="btn primary" onClick=${() => apply(s)}>${t("apply")}</button></div>`)}` : null}
      ${data.agents_by_project?.length ? html`<div class="label section">${t("agent_skill")}</div>
        <div class="card table-wrap" style="margin-top:8px"><table class="table">
          <tr><th>${t("project")}</th><th>${t("agent")}</th><th>${t("tasks")}</th><th>${t("success")}</th><th>${t("tests")}</th><th>${t("review_ok")}</th><th>${t("quality")}</th><th>${t("minutes_unit")}</th></tr>
          ${data.agents_by_project.map((r) => html`<tr><td>${r.project}</td><td>${r.agent}</td><td>${r.tasks}</td>
            <td>${Math.round(r.success * 100)}%</td><td>${r.tests == null ? "–" : `${Math.round(r.tests * 100)}%`}</td>
            <td>${r.approved == null ? "–" : `${Math.round(r.approved * 100)}%`}</td>
            <td title=${[r.reverted && `${t("sc_rolled_back")}: ${r.reverted}`, r.regressions && `${t("sc_regressions")}: ${r.regressions}`, r.review_rounds && `${t("sc_rounds")}: ${r.review_rounds}`].filter(Boolean).join(" · ")}>${Math.round(r.quality * 100)}%</td>
            <td>${r.minutes}</td></tr>`)}
        </table></div>` : null}
      ${data.scorecard?.some((w) => w.tasks) ? html`<div class="label section">${t("scorecard")}</div>
        <div class="card table-wrap" style="margin-top:8px"><table class="table">
          <tr><th>${t("sc_week")}</th><th>${t("tasks")}</th><th>${t("success")}</th><th>${t("col_discarded")}</th><th>${t("sc_rolled_back")}</th>
            <th>${t("sc_rescue")}</th><th>${t("sc_rounds")}</th><th>${t("sc_minutes")}</th><th>${t("incidents")}</th><th>${t("sc_regressions")}</th></tr>
          ${data.scorecard.map((w) => html`<tr><td class="mono" style="white-space:nowrap">${w.week}</td><td>${w.tasks}</td><td>${pct(w.success)}</td><td>${w.discarded}</td>
            <td>${w.rolled_back}</td><td>${pct(w.retry_rescue)}</td><td>${w.review_rounds ?? "–"}</td><td>${w.minutes_per_task ?? "–"}</td>
            <td style=${w.incidents ? "color:var(--danger)" : ""}>${w.incidents}</td><td style=${w.regressions ? "color:var(--warn)" : ""}>${w.regressions}</td></tr>`)}
        </table></div>` : null}
    </div>`;
}
