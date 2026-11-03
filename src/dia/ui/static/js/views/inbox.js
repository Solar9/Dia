import { useEffect, useState } from "preact/hooks";
import { html } from "../html.js";
import { api } from "../api.js";
import { t } from "../i18n.js";
import { Icon, Pill } from "../ui/icons.js";
import { confirmDialog, promptDialog } from "../ui/dialog.js";
import { Resource, useResource } from "../ui/resource.js";
import { VSplitter } from "../ui/splitter.js";
import { SPLIT_INBOX, ago, clock, firstLine, localeOf, useSplitWidth, useTick } from "../util.js";
import { Composer, RUNNING, decisionOf } from "./tasks.js";

export function InboxCard({ task, kind, open, toast, reload }) {
  const [busy, setBusy] = useState(false);
  const d = task.details || {};
  const blocked = (d.violations || []).length || (d.verification?.checks || []).some((c) => c.held === false);
  const act = async (action, body) => {
    setBusy(true);
    try {
      const result = await api(`/api/tasks/${task.id}/${action}`, { method: "POST", body });
      toast(result.message || result.status || action);
      if (result.url) window.open(result.url, "_blank");
      reload();
    } catch (e) { toast(e.message, "error"); }
    setBusy(false);
  };
  const decide = async (action) => {
    const reason = await promptDialog(t("reason_prompt"), "");
    if (reason !== null) act(action, { reason });
  };
  const label = { merge: t("ready_to_merge"), plan: t("plan_to_approve"), ci: t("ci_failed"), comments: t("comments_waiting") }[kind];
  const tone = { merge: "ok", plan: "info", ci: "danger", comments: "warn" }[kind];
  return html`
    <article class="inbox-card ${kind === "ci" ? "alert" : ""}">
      <div class="inbox-meta"><span class="dot ${tone}"></span><span>${task.project}</span><span class="sep">/</span>
        <span class="mono">${task.id}</span><span class="sep">·</span><span>${task.agent} · ${ago(task.created_at)}</span>
        <span class="spacer"></span>
        ${task.diffstat ? html`<span class="mono stat" title=${t("files_changed", { n: task.diffstat.files })}><span class="tone-ok">+${task.diffstat.added}</span> <span class="tone-danger">−${task.diffstat.removed}</span></span>` : null}
        <span class="tone-${tone}">${label}</span></div>
      <button class="inbox-title" onClick=${() => open(task.id)}>${d.scenario || firstLine(task.prompt)}</button>
      ${kind === "merge" ? html`<div class="inbox-checks">
        ${task.tests_ok ? html`<span class="tone-ok"><${Icon} name="check" size=${13} />${t("tests")}: ${t("passed")}</span>` : null}
        ${task.tests_ok === false ? html`<span class="tone-danger">${t("tests")}: FAILED</span>` : null}
        ${d.reviews?.length ? html`<span class="muted">${t("reviews")}: ${d.reviews[d.reviews.length - 1].verdict.replace("_", " ")}</span>` : null}
        ${task.branch ? html`<span class="mono faint">${task.branch}</span>` : null}</div>` : null}
      ${kind === "plan" && d.plan ? html`<ol class="inbox-steps">${d.plan.slice(0, 3).map((s) => html`<li>${s.title || s.agent}</li>`)}
        ${d.plan.length > 3 ? html`<li class="faint">+${d.plan.length - 3}</li>` : null}</ol>` : null}
      ${kind === "ci" && d.ci?.failed?.length ? html`<div class="inbox-checks">${d.ci.failed.map((f) => html`<a class="tone-danger mono" href=${f.url} target="_blank">✕ ${f.name}</a>`)}</div>` : null}
      <div class="row">
        ${kind === "merge" && !blocked ? html`<button class="btn primary" disabled=${busy} onClick=${() => decide("merge")}>${t("merge")}</button>` : null}
        ${kind === "merge" && blocked ? html`<span class="tone-warn">⚠ ${t("needs_override")}</span>` : null}
        ${kind === "plan" ? html`<button class="btn primary" disabled=${busy} onClick=${() => act("run-plan")}>${t("run_plan")}</button>` : null}
        ${kind === "ci" ? html`<button class="btn primary" disabled=${busy} onClick=${() => act("fix-ci")}>${t("fix_ci")}</button>` : null}
        ${kind === "comments" ? html`<button class="btn primary" disabled=${busy} onClick=${() => act("address-comments")}>${t("address")} (${d.comments_pending.length})</button>` : null}
        <button class="btn" onClick=${() => open(task.id)}>${kind === "merge" ? t("review_changes") : t("open_task")} <${Icon} name="arrow" size=${14} /></button>
        ${kind === "merge" && !blocked ? html`<button class="btn" disabled=${busy} onClick=${() => act("publish")}>${t("publish")}</button>` : null}
        <span class="spacer"></span>
        ${kind === "merge" || kind === "plan" ? html`<button class="btn ghost danger" disabled=${busy} onClick=${() => decide("discard")}>${t("discard")}</button>` : null}
      </div>
    </article>`;
}

export function MissionCard({ open }) {
  const res = useResource("/api/missions", { interval: 30000 });
  return html`<${Resource} res=${res} quiet empty=${(list) => !liveOf(list)}>${(list) => html`<${MissionBody} mission=${liveOf(list)} open=${open} />`}<//>`;
}

const liveOf = (missions) => {
  const live = (missions || []).filter((m) => !["merged", "discarded"].includes(m.status));
  return live.find((m) => m.status === "running") || live[0];
};

function MissionBody({ mission, open }) {
  const steps = mission.details.mission.steps;
  const done = steps.filter((x) => x.status === "done").length;
  const current = steps.find((x) => x.status === "running") || steps.find((x) => x.status === "pending");
  return html`<div class="card side-card">
    <div class="row"><span class="label">${t("mission")}</span><span class="spacer"></span>
      <button class="btn ghost" onClick=${() => open("missions")}>${t("open_view")}</button></div>
    <div>${firstLine(mission.prompt)}</div>
    <div class="steps-bar" role="img" aria-label=${`${done}/${steps.length}`}>
      ${steps.map((x) => html`<span class="step-seg ${x.status}"></span>`)}</div>
    <div class="faint">${done}/${steps.length}${current ? ` · ${current.title}` : ""} · <${Pill} status=${mission.status} /></div>
  </div>`;
}

export function AgentsCard({ status }) {
  const res = useResource("/api/usage?days=1&weeks=1", { interval: 60000 });
  const usage = res.data;
  if (!status) return null;
  const today = Object.fromEntries((usage?.per_agent || usage?.agents || []).map((a) => [a.agent, a]));
  return html`<div class="card side-card">
    <span class="label">${t("agents")}</span>
    ${res.error ? html`<div class="state error small" role="alert">${t("load_failed")}: ${res.error}</div>` : null}
    ${status.agents.map((a) => {
      const used = today[a.name];
      const state = a.limited_until ? "warn" : a.ok ? "ok" : "danger";
      return html`<div class="agent-line" title=${a.problem || ""}>
        <span class="dot ${state}"></span><span class="agent-name">${a.name}</span>
        <span class="faint">${a.limited_until ? t("limited_until", { time: clock(a.limited_until) })
          : !a.ok ? t("agent_unavailable")
          : used ? t("calls_today", { n: used.calls, min: used.minutes }) : t("idle_today")}</span></div>`;
    })}
  </div>`;
}

export function InboxView({ loading, tasks, status, open, toast, reload, go }) {
  useTick(30000);
  const [sideW, setSideW, commitSideW] = useSplitWidth(SPLIT_INBOX, 320, 240, 480);
  const waiting = tasks.map((x) => [x, decisionOf(x)]).filter(([, kind]) => kind)
    .sort(([a], [b]) => a.created_at.localeCompare(b.created_at));
  const running = tasks.filter((x) => RUNNING.includes(x.status));
  const waitingCount = status?.counts ? status.counts.waiting_for_you : waiting.length;
  const today = new Date().toLocaleDateString(localeOf(), { weekday: "long", day: "numeric", month: "long" });
  return html`
    <div class="page wide inbox">
      <div class="page-head">
        <div class="eyebrow">${today}</div>
        <h1>${t("inbox")}</h1>
        <p class="muted">${loading ? t("loading") : waitingCount ? t("inbox_waiting", { n: waitingCount }) : t("inbox_clear")}</p>
      </div>
      <${Composer} status=${status} toast=${toast} onCreated=${(task) => { reload(); open(task.id); }} />
      <div class="inbox-cols" style=${{ "--inbox-side-w": `${sideW}px` }}>
        <section class="inbox-main">
          <h2>${t("waiting_for_you")}</h2>
          ${waiting.length ? waiting.map(([x, kind]) => html`<${InboxCard} key=${x.id} task=${x} kind=${kind} open=${open} toast=${toast} reload=${reload} />`)
            : loading ? html`<div class="state loading" role="status">${t("loading")}</div>`
            : html`<div class="card faint">${t("inbox_clear")}</div>`}
        </section>
        <${VSplitter} width=${sideW} setWidth=${setSideW} commit=${commitSideW} min=${240} max=${480} def=${320} reverse />
        <aside class="inbox-side">
          <h2>${t("working_now")}</h2>
          <div class="card flush">
            ${running.length ? running.map((x) => html`<button key=${x.id} class="run-row" onClick=${() => open(x.id)}>
              <span class="dot warn pulse"></span>
              <span class="run-text"><span>${firstLine(x.prompt)}</span>
                <span class="faint">${x.project} · ${x.agent} · ${x.status === "running" ? t("running_for", { time: ago(x.created_at) }) : x.status}</span></span></button>`)
              : html`<div class="run-row faint">${t("nothing_running")}</div>`}
          </div>
          <${MissionCard} open=${go} />
          <${AgentsCard} status=${status} />
        </aside>
      </div>
    </div>`;
}
