import { useEffect, useState } from "preact/hooks";
import { html } from "../html.js";
import { api } from "../api.js";
import { t } from "../i18n.js";
import { Meter } from "../ui/charts.js";
import { Pill } from "../ui/icons.js";
import { ResourceState, useResource } from "../ui/resource.js";
import { VSplitter } from "../ui/splitter.js";
import { SPLIT_MISSIONS, ago, clock, firstLine, useSplitWidth } from "../util.js";

export function stepLevels(steps) {
  const byId = Object.fromEntries(steps.map((s) => [s.id, s]));
  const level = {};
  const visit = (id) => (level[id] ??= 1 + Math.max(-1, ...byId[id].depends_on.map(visit)));
  steps.forEach((s) => visit(s.id));
  const columns = [];
  steps.forEach((s) => (columns[level[s.id]] ||= []).push(s));
  return columns;
}

export function Activity() {
  const [rows, setRows] = useState([]);
  const res = useResource("/api/audit?limit=40", { on: setRows });
  useEffect(() => {
    const add = (e) => setRows((all) => [e.detail, ...all].slice(0, 60));
    window.addEventListener("dia-audit", add);
    return () => window.removeEventListener("dia-audit", add);
  }, []);
  return html`<div class="activity"><${ResourceState} res=${res} />${rows.map((r) => html`<div class="activity-row">
    <span class="faint">${clock(r.at)}</span><span class="mono">${r.action}</span>
    <span class="muted">${r.actor}</span><span class="activity-detail">${r.detail || r.target || ""}</span></div>`)}
    ${rows.length || !res.data ? null : html`<p class="muted">${t("no_activity")}</p>`}</div>`;
}

export function GoalsCard({ status, toast }) {
  const res = useResource("/api/goals");
  const goals = res.data || [];
  const [text, setText] = useState("");
  const [weeks, setWeeks] = useState("");
  const [busy, setBusy] = useState(false);
  const load = res.reload;
  const call = async (path, body) => {
    setBusy(true);
    try { await api(path, { method: "POST", body }); await load(); } catch (e) { toast(e.message, "error"); }
    setBusy(false);
  };
  const project = status?.projects[0]?.name;
  const create = () => { call("/api/goals", { project, goal: text, weeks }); setText(""); };
  return html`<div class="goals"><div class="label">${t("goals")}</div><${ResourceState} res=${res} quiet />
    <div class="composer goal-form">
      <input class="goal-input" placeholder=${t("goal_new")} aria-label=${t("goal_new")} value=${text} onInput=${(e) => setText(e.target.value)}
        onKeyDown=${(e) => { if (e.key === "Enter" && text.trim() && project) create(); }} />
      <div class="composer-bar">
        <label class="chip-number" title=${t("goal_weeks")}><span>${t("goal_weeks")}</span>
          <input type="number" min="1" placeholder="4" value=${weeks} onInput=${(e) => setWeeks(e.target.value)} /></label>
        <span class="spacer"></span>
        <button class="btn" disabled=${busy || !text.trim() || !project} onClick=${create}>${t("goal_create")}</button>
      </div></div>
    ${goals.filter((g) => g.status !== "failed").map((g) => {
      const review = (g.details.reviews || []).slice(-1)[0];
      const ms = g.details.milestones || [];
      return html`<div class="card" style="margin-top:8px"><div class="row"><strong style="flex:1">${g.prompt}</strong><${Pill} status=${g.status === "active" ? "running" : "done"} label=${g.status} /></div>
        <div class="faint">${g.project}${g.details.deadline ? ` · ${g.details.deadline}` : ""} · ${ms.filter((m) => m.status === "done").length}/${ms.length}</div>
        ${ms.map((m, i) => html`<div>${m.status === "done" ? "✓" : "○"} ${i + 1}. ${m.title}</div>`)}
        ${review ? html`<p class="muted" style="margin:6px 0">${review.progress}</p>
          ${review.blockers.length ? html`<div class="faint">${t("blockers")}: ${review.blockers.join("; ")}</div>` : null}
          ${review.next ? html`<div>${t("goal_next")}: ${review.next.mission}</div>` : null}` : null}
        ${g.status === "active" ? html`<div class="row" style="margin-top:8px"><button class="btn ghost" disabled=${busy} onClick=${() => call(`/api/goals/${g.id}/review`)}>${t("goal_review")}</button>
          ${review?.status === "proposed" ? html`<button class="btn primary" disabled=${busy} onClick=${() => call(`/api/goals/${g.id}/approve`)}>${t("goal_approve")}</button>` : null}</div>` : null}
      </div>`;
    })}</div>`;
}

export function MissionsView({ status, toast, open }) {
  const res = useResource("/api/missions");
  const missions = res.data || [];
  const [selected, setSelected] = useState(null);
  const [form, setForm] = useState({ project: "", goal: "", calls: "", minutes: "", priority: "normal" });
  const [busy, setBusy] = useState(false);
  const [listW, setListW, commitListW] = useSplitWidth(SPLIT_MISSIONS, 360, 260, 560);
  const load = res.reload;
  useEffect(() => {
    const onTask = (e) => { if (e.detail.mode === "mission" || e.detail.details?.mission) load(); };
    window.addEventListener("dia-task", onTask);
    return () => window.removeEventListener("dia-task", onTask);
  }, []);
  const create = async () => {
    setBusy(true);
    try {
      const m = await api("/api/missions", { method: "POST", body: { ...form, project: form.project || status.projects[0]?.name } });
      setForm({ ...form, goal: "" }); await load(); setSelected(m.id);
    } catch (e) { toast(e.message, "error"); }
    setBusy(false);
  };
  const act = async (path, body) => {
    try { const r = await api(path, { method: "POST", body }); if (r?.message) toast(r.message); load(); }
    catch (e) { toast(e.message, "error"); }
  };
  const mission = missions.find((m) => m.id === selected);
  return html`
    <div class="split ${selected ? "has-selected" : ""}" style=${{ "--list-w": `${listW}px` }}>
      <div class="list">
        <div class="composer">
          <textarea class="textarea" rows="3" placeholder=${t("mission_goal")} value=${form.goal} aria-label=${t("mission_goal")}
            onInput=${(e) => setForm({ ...form, goal: e.target.value })}
            onKeyDown=${(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && form.goal.trim()) create(); }}></textarea>
          <div class="composer-bar">
            <select class="chip-select" title=${t("project")} value=${form.project || status?.projects[0]?.name} onChange=${(e) => setForm({ ...form, project: e.target.value })}>
              ${(status?.projects || []).map((p) => html`<option value=${p.name}>${p.name}</option>`)}</select>
            <select class="chip-select" title=${t("priority")} value=${form.priority} onChange=${(e) => setForm({ ...form, priority: e.target.value })}>
              ${["low", "normal", "high"].map((p) => html`<option value=${p}>${t(`prio_${p}`)}</option>`)}</select>
            <label class="chip-number" title=${t("budget_calls")}><span>${t("budget_calls_short")}</span>
              <input type="number" min="0" placeholder="∞" value=${form.calls} onInput=${(e) => setForm({ ...form, calls: e.target.value })} /></label>
            <label class="chip-number" title=${t("budget_minutes")}><span>${t("budget_minutes_short")}</span>
              <input type="number" min="0" placeholder="∞" value=${form.minutes} onInput=${(e) => setForm({ ...form, minutes: e.target.value })} /></label>
            <span class="spacer"></span>
            <button class="btn primary" disabled=${busy || !form.goal.trim()} onClick=${create}>${busy ? t("planning") : t("plan_mission")}</button>
          </div>
        </div>
        <${GoalsCard} status=${status} toast=${toast} />
        <${ResourceState} res=${res} />
        ${missions.map((m) => {
          const steps = m.details.mission.steps;
          const done = steps.filter((s) => s.status === "done").length;
          return html`<button class="task-row ${m.id === selected ? "active" : ""}" onClick=${() => setSelected(m.id)}>
            <span class="task-title">${firstLine(m.prompt)}</span><${Pill} status=${m.status} />
            <span class="task-meta">${m.project} · ${done}/${steps.length} · ${t(`prio_${m.details.mission.priority || "normal"}`)} · ${ago(m.created_at)}</span>
            <span class="progress"><span style=${`width:${(100 * done) / steps.length}%`}></span></span>
          </button>`;
        })}
        ${missions.length || !res.data ? null : html`<div class="empty">${t("no_missions")}</div>`}
      </div>
      <${VSplitter} width=${listW} setWidth=${setListW} commit=${commitListW} min=${260} max=${560} def=${360} />
      ${mission ? html`<div class="detail">
        <button class="btn ghost back" onClick=${() => setSelected(null)}>← ${t("missions")}</button>
        <div class="row"><${Pill} status=${mission.status} /><span class="faint mono">${mission.id}</span></div>
        <h2>${firstLine(mission.prompt)}</h2>
        ${mission.error ? html`<div class="card" style="color:var(--danger)">${mission.error}</div>` : null}
        <div class="row section">
          ${["planned", "paused", "failed"].includes(mission.status) ? html`<button class="btn primary" onClick=${() => act(`/api/tasks/${mission.id}/run-plan`)}>${mission.status === "planned" ? t("start_mission") : t("continue_mission")}</button>` : null}
          ${mission.status === "running" ? html`<button class="btn" onClick=${() => act(`/api/missions/${mission.id}/cancel`)}>${t("cancel_mission")}</button>` : null}
          ${mission.status === "done" && mission.commit_sha ? html`
            <button class="btn" onClick=${() => open(mission.id)}>${t("review_changes")}</button>
            <button class="btn primary" onClick=${() => act(`/api/tasks/${mission.id}/merge`)}>${t("merge")}</button>
            <button class="btn" onClick=${() => act(`/api/tasks/${mission.id}/publish`)}>${t("publish")}</button>
            <button class="btn danger" onClick=${() => act(`/api/tasks/${mission.id}/discard`)}>${t("discard")}</button>` : null}
        </div>
        <div class="grid section">
          <${Meter} label=${t("budget_calls")} used=${mission.budget.used.calls} limit=${mission.budget.limits.calls} unit="" />
          <${Meter} label=${t("budget_minutes")} used=${mission.budget.used.minutes} limit=${mission.budget.limits.minutes} unit="min" />
        </div>
        <div class="label section">${t("steps")}</div>
        <div class="graph">${stepLevels(mission.details.mission.steps).map((column) => html`<div class="graph-col">
          ${column.map((s) => html`<div class="card step">
            <div class="row" style="justify-content:space-between"><strong>${s.title}</strong><${Pill} status=${s.status} /></div>
            <div class="muted">${s.agent}${s.depends_on.length ? ` · ${t("after")} ${s.depends_on.join(", ")}` : ""}</div>
            ${s.error ? html`<div style="color:var(--danger);font-size:12px">${s.error}</div>` : null}
            ${s.task_id ? html`<button class="btn ghost" onClick=${() => open(s.task_id)}>${t("open_task")}</button>` : null}
          </div>`)}</div>`)}</div>
        <div class="label section">${t("mission_log")}</div>
        <div class="card">${[...mission.details.mission.log].reverse().map((e) => html`<div class="activity-row log-row"><span class="faint">${clock(e.at)}</span><span>${e.text}</span></div>`)}</div>
      </div>` : html`<div class="detail"><div class="label">${t("activity")}</div><${Activity} /></div>`}
    </div>`;
}
