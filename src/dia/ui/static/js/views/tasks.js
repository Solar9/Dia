import { useCallback, useEffect, useRef, useState } from "preact/hooks";
import { html } from "../html.js";
import { api } from "../api.js";
import { t, tStatus } from "../i18n.js";
import { Diff, parseUnifiedDiff } from "../ui/diff.js";
import { Icon, Pill } from "../ui/icons.js";
import { confirmDialog, promptDialog } from "../ui/dialog.js";
import { RichText } from "../ui/richtext.js";
import { VSplitter } from "../ui/splitter.js";
import { SPLIT_TASKS, STATUS_ORDER, ago, clock, firstLine, useSplitWidth, useTick } from "../util.js";

export function Composer({ status, onCreated, toast }) {
  const projects = status?.projects || [];
  const [project, setProject] = useState("");
  const [agent, setAgent] = useState("");
  const [model, setModel] = useState("");
  const agentInfo = (status?.agents || []).find((a) => a.name === agent);
  const spec = agent && model ? `${agent}:${model}` : agent;
  const [mode, setMode] = useState("edit");
  const [review, setReview] = useState(false);
  const [pipeline, setPipeline] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const chosen = project || projects[0]?.name || "";

  const submit = async (kind) => {
    if (!text.trim()) return;
    if (kind !== "research" && !chosen) return;
    setBusy(true);
    try {
      if (kind === "research") {
        const task = await api("/api/research", {
          method: "POST",
          body: { topic: text, project: chosen || null, agent: spec || undefined },
        });
        setText(""); onCreated(task); toast(t("research_started")); setBusy(false);
        return;
      }
      if (kind === "council") {
        await api("/api/council", { method: "POST", body: { question: text, project: chosen } });
        setText(""); toast(t("council_started")); setBusy(false);
        return;
      }
      if (kind === "scenario") {
        const task = await api("/api/scenarios", { method: "POST", body: { project: chosen, scenario: text, agent: spec || undefined } });
        setText(""); onCreated(task); toast(t("started")); setBusy(false);
        return;
      }
      const task = kind === "plan"
        ? await api("/api/plans", { method: "POST", body: { project: chosen, goal: text, pipeline, planner: spec || undefined } })
        : await api("/api/tasks", { method: "POST", body: { project: chosen, prompt: text, agent, mode, review: review || undefined, model: (agent && model) || undefined } });
      setText("");
      onCreated(task);
      toast(t("started"));
    } catch (e) { toast(e.message, "error"); }
    setBusy(false);
  };

  return html`
    <div class="composer">
      <textarea class="textarea" placeholder=${t("what")} value=${text} aria-label=${t("what")}
        onInput=${(e) => setText(e.target.value)}
        onKeyDown=${(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submit("run"); }}></textarea>
      <div class="composer-bar">
        <select class="chip-select" value=${chosen} title=${t("project")} onChange=${(e) => setProject(e.target.value)}>
          ${projects.length ? null : html`<option value="">—</option>`}
          ${projects.map((p) => html`<option value=${p.name}>${p.name}</option>`)}
        </select>
        <select class="chip-select" value=${agent} title=${t("agent")} onChange=${(e) => { setAgent(e.target.value); setModel(""); }}>
          <option value="">${t("default_agent")}</option>
          ${(status?.agents || []).map((a) => html`<option value=${a.name}>${a.name}</option>`)}
        </select>
        ${agentInfo ? html`<input class="chip-select" style="width:130px" list="task-models" placeholder=${`${t("model")}: ${agentInfo.model || t("auto")}`}
            value=${model} onInput=${(e) => setModel(e.target.value)} />
          <datalist id="task-models">${agentInfo.models.map((m) => html`<option value=${m}></option>`)}</datalist>` : null}
        <select class="chip-select" value=${mode} title=${t("mode")} onChange=${(e) => setMode(e.target.value)}>
          <option value="edit">${t("edit")}</option>
          <option value="read-only">${t("read_only")}</option>
        </select>
        ${status?.pipelines?.length ? html`
          <select class="chip-select" value=${pipeline} onChange=${(e) => setPipeline(e.target.value)}>
            <option value="">${t("planner")}</option>
            ${status.pipelines.map((p) => html`<option value=${p}>${t("pipeline")}: ${p}</option>`)}
          </select>` : null}
        <label class="chip-check"><input type="checkbox" checked=${review}
          onChange=${(e) => setReview(e.target.checked)} /> ${t("review")}</label>
        <span class="spacer"></span>
        <button class="btn ghost" title=${t("research_help")} disabled=${busy || !text.trim()} onClick=${() => submit("research")}>${t("research")}</button>
        <button class="btn ghost" title=${t("scenario_help")} disabled=${busy || !text.trim() || !chosen} onClick=${() => submit("scenario")}>${t("scenario")}</button>
        <button class="btn ghost" title=${t("council_help")} disabled=${busy || !text.trim() || !chosen} onClick=${() => submit("council")}>${t("council")}</button>
        <button class="btn" disabled=${busy || !text.trim() || !chosen} onClick=${() => submit("plan")}>${t("plan")}</button>
        <button class="btn primary" title="Ctrl+↵" disabled=${busy || !text.trim() || !chosen} onClick=${() => submit("run")}>${t("run")}</button>
      </div>
    </div>`;
}

export function TaskDetail({ id, toast, onChanged, onBack }) {
  const [task, setTask] = useState(null);
  const [diff, setDiff] = useState(null);
  const [log, setLog] = useState(null);
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState(null);
  const [filesOpen, setFilesOpen] = useState(false);
  const [focusPath, setFocusPath] = useState(null);
  const asked = useRef({});

  const load = useCallback(() => api(`/api/tasks/${id}`).then(setTask).catch((e) => toast(e.message, "error")), [id]);
  useEffect(() => {
    setDiff(null); setLog(null); setTab(null); setFilesOpen(false); setFocusPath(null); asked.current = {}; load();
  }, [id]);
  useEffect(() => {
    const onUpdate = (e) => {
      if (e.detail.id !== id) return;
      asked.current = {};  // a new commit or test run: fetch them again when shown
      load();
    };
    window.addEventListener("dia-task", onUpdate);
    return () => window.removeEventListener("dia-task", onUpdate);
  }, [id]);

  if (!task) return html`<div class="empty">…</div>`;
  const d = task.details || {};
  const act = async (action, body) => {
    setBusy(true);
    try {
      const result = await api(`/api/tasks/${id}/${action}`, { method: "POST", body });
      toast(result.message || result.status || action);
      if (result.url) window.open(result.url, "_blank");
      load(); onChanged();
    } catch (e) { toast(e.message, "error"); }
    setBusy(false);
  };
  const blockers = [
    ...(d.violations || []).map((v) => `${v.rule} (${v.where})`),
    ...((d.verification?.checks || []).filter((c) => c.held === false).map((c) => c.assumption)),
  ];
  const decide = async (action) => {
    let override;
    if (action === "merge" && blockers.length && !d.override) {
      override = await promptDialog(t("override_prompt"), "");
      if (!override) return;
    }
    const reason = await promptDialog(t("reason_prompt"), "");
    if (reason !== null) act(action, { reason, override });
  };
  const reviewable = task.commit_sha && ["done", "failed"].includes(task.status);
  const ci = d.ci || {};
  const pending = d.comments_pending || [];
  const tests = task.tests_ok === null ? t("not_run") : task.tests_ok ? t("passed") : "FAILED";

  const changes = task.commit_sha && !["merged", "discarded"].includes(task.status);
  const reviewed = d.reviews?.length || pending.length;
  const tabs = [["summary", t("summary_tab")], changes && ["changes", t("changes_tab")],
    task.has_test_log && ["tests", t("tests")], reviewed && ["review", t("reviews")]].filter(Boolean);
  const shown = tab && tabs.some(([key]) => key === tab) ? tab
    : changes && task.status === "done" ? "changes" : "summary";
  const loadDiff = () => {
    if (asked.current.diff) return;
    asked.current.diff = true;
    api(`/api/tasks/${id}/diff`).then(setDiff).catch((e) => { setDiff(""); toast(e.message, "error"); });
  };
  // Prefetch the diff whenever there are changes, so the file menu in the
  // decision bar can open without waiting for the Changes tab.
  if (changes && diff === null) loadDiff();
  if (shown === "tests" && !asked.current.log) {
    asked.current.log = true;
    api(`/api/tasks/${id}/tests`).then(setLog).catch((e) => { setLog(""); toast(e.message, "error"); });
  }
  const lastReview = d.reviews?.length ? d.reviews[d.reviews.length - 1] : null;
  const diffFiles = typeof diff === "string" && diff ? parseUnifiedDiff(diff) : [];
  const pickFile = (path) => {
    setTab("changes");
    setFocusPath(path);
  };
  const toggleFiles = () => {
    setTab("changes");
    loadDiff();
    setFilesOpen((was) => !was);
  };

  return html`
    <div class="detail">
      <button class="btn ghost back" onClick=${onBack}>← ${t("tasks")}</button>
      <div class="detail-head">
        <div class="inbox-meta"><span class="dot ${task.status === "failed" ? "danger" : RUNNING.includes(task.status) ? "warn" : "ok"}"></span>
          <span>${task.project}</span><span class="sep">/</span><span class="mono">${task.id}</span><span class="sep">·</span><span>${ago(task.created_at)}</span></div>
        <div class="title-row"><h2>${d.scenario ? d.scenario : firstLine(task.prompt)}</h2><${Pill} status=${task.status} /></div>
        ${task.status === "waiting" && d.waiting_until ? html`<span class="muted">${t("waiting_until", { time: clock(d.waiting_until) })}</span>` : null}
        ${d.scenario_result ? html`<div class="row"><${Pill} status=${d.scenario_result === "works" ? "done" : d.scenario_result === "broken" ? "failed" : "planned"} label=${t(`scenario_${d.scenario_result}`)} /></div>` : null}
        <div class="chips">
          <span class="chip">${task.agent} · ${task.mode}</span>
          ${task.branch ? html`<span class="chip mono">${task.branch}${task.commit_sha ? ` @ ${task.commit_sha.slice(0, 10)}` : ""}</span>` : null}
          ${d.published ? html`<span class="chip">${t("ci")}: ${ci.state || "-"}${d.published.url ? html` · <a href=${d.published.url} target="_blank">${t("open_pr")}</a>` : null}</span>` : null}
          ${d.routed ? html`<span class="chip">${t("routed")}: ${d.routed}</span>` : null}
          ${d.reverts ? html`<span class="chip">${t("reverts")}: <span class="mono">${d.reverts}</span></span>` : null}
          ${d.reverted_by ? html`<span class="chip">${t("reverted_by")}: <span class="mono">${d.reverted_by}</span></span>` : null}
        </div>
      </div>
      <div class=${`decision-bar${filesOpen ? " files-open" : ""}`}>
        <div class="decision-bar-top">
          <div class="decision-checks">
            ${task.tests_ok !== null ? html`<span class=${task.tests_ok ? "tone-ok" : "tone-danger"}>${task.tests_ok ? html`<${Icon} name="check" size=${13} />` : "✕"} ${t("tests")}: ${tests}</span>` : null}
            ${lastReview ? html`<span class="muted">${lastReview.reviewer}: ${lastReview.verdict.replace("_", " ")}</span>` : null}
            ${task.diffstat ? html`<span class="mono decision-diffstat">
              <span class="tone-ok">+${task.diffstat.added}</span>
              <span class="tone-danger">−${task.diffstat.removed}</span>
              <button type="button" class=${`diff-files-trigger${filesOpen ? " open" : ""}`} aria-expanded=${filesOpen}
                title=${t("diff_file_list")} onClick=${toggleFiles}>
                <span>· ${t("files_changed", { n: task.diffstat.files })}</span>
                <span class="diff-files-caret" aria-hidden="true">
                  <${Icon} name=${filesOpen ? "chevronUp" : "chevronDown"} size=${16} /></span>
              </button>
            </span>` : null}
          </div>
          <div class="decision-actions">
            ${task.status === "planned" ? html`<button class="btn primary" disabled=${busy} onClick=${() => act("run-plan")}>${t("run_plan")}</button>` : null}
            ${reviewable ? html`
              <button class="btn" disabled=${busy} onClick=${() => act("review")}>${t("review")}</button>
              <button class="btn primary" disabled=${busy || task.status !== "done"} onClick=${() => decide("merge")}>${t("merge")}</button>
              <button class="btn" disabled=${busy || task.status !== "done"} onClick=${() => act("publish")}>${t("publish")}</button>
              <button class="btn danger" disabled=${busy} onClick=${() => decide("discard")}>${t("discard")}</button>` : null}
            ${task.status === "planned" ? html`<button class="btn danger" disabled=${busy} onClick=${() => decide("discard")}>${t("discard")}</button>` : null}
            ${task.status === "published" && ci.state === "failed" ? html`<button class="btn primary" disabled=${busy} onClick=${() => act("fix-ci")}>${t("fix_ci")}</button>` : null}
            ${task.status === "published" && pending.length ? html`<button class="btn primary" disabled=${busy} onClick=${() => act("address-comments")}>${t("address")} (${pending.length})</button>` : null}
            ${task.mode === "build" && task.status === "done" && !d.published?.itch ? html`<button class="btn primary" disabled=${busy} onClick=${async () => (await confirmDialog(t("publish_itch_confirm"))) && act("publish-itch")}>${t("publish_itch")}</button>` : null}
            ${task.mode === "build" && task.status === "done" && !d.published?.steam ? html`<button class="btn" disabled=${busy} onClick=${async () => (await confirmDialog(t("publish_steam_confirm"))) && act("publish-steam")}>${t("publish_steam")}</button>` : null}
            ${task.status === "merged" && d.merge_commit && !d.reverted_by ? html`<button class="btn danger" disabled=${busy} onClick=${async () => (await confirmDialog(t("rollback_confirm"), { danger: true })) && decide("rollback")}>${t("rollback")}</button>` : null}
            ${task.mode === "edit" && ["done", "merged", "published"].includes(task.status) && !d.howto ? html`<button class="btn ghost" disabled=${busy} onClick=${() => act("howto")}>${t("save_howto")}</button>` : null}
            ${task.mode === "check" && task.tests_ok === false && !d.fix_task ? html`<button class="btn primary" disabled=${busy} onClick=${() => act("fix-build")}>${t("fix_build")}</button>` : null}
          </div>
        </div>
        ${filesOpen ? html`<div class="decision-files-panel">
          <div class="decision-files" role="listbox" aria-label=${t("diff_file_list")}>
            ${diff === null ? html`<div class="diff-files-empty faint">…</div>`
              : diffFiles.length ? diffFiles.map((f) => html`<button type="button" key=${f.path} role="option"
                class=${`diff-files-item ${f.path === focusPath ? "active" : ""}`}
                onClick=${() => pickFile(f.path)}>
                <span class="diff-path mono" title=${f.path}>${f.path}</span>
                <span class="mono diff-stat">
                  ${f.added ? html`<span class="tone-ok">+${f.added}</span>` : null}
                  ${f.removed ? html`<span class="tone-danger">−${f.removed}</span>` : null}
                </span>
              </button>`)
              : html`<div class="diff-files-empty faint">${t("diff_empty")}</div>`}
          </div>
          <button type="button" class="decision-files-fold" title=${t("diff_collapse")}
            aria-label=${t("diff_collapse")} onClick=${() => setFilesOpen(false)}>
            <span class="diff-files-caret" aria-hidden="true"><${Icon} name="chevronUp" size=${14} /></span>
          </button>
        </div>` : null}
      </div>
      <div class="tabs" role="tablist">
        ${tabs.map(([key, label]) => html`<button role="tab" aria-selected=${shown === key} class="tab ${shown === key ? "active" : ""}" onClick=${() => setTab(key)}>${label}</button>`)}
      </div>
      ${shown === "changes" ? html`<div>
        ${lastReview ? html`<div class="review-note"><strong>${lastReview.reviewer}</strong> <span class="faint">· ${lastReview.verdict.replace("_", " ")}</span>
          <${RichText} text=${lastReview.findings} class="prose muted" /></div>` : null}
        ${diff === null ? html`<div class="faint">…</div>`
          : html`<${Diff} text=${diff} notes=${pending} focusPath=${focusPath} onFocused=${() => setFocusPath(null)} />`}</div>` : null}
      ${shown === "tests" ? html`<pre class="log mono">${log ?? "…"}</pre>` : null}
      ${shown === "review" ? html`<div>
      ${d.reviews?.length ? html`<div class="section"><div class="label">${t("reviews")}</div>
        ${d.reviews.map((r) => html`<div class="card" style="margin-bottom:8px">
          <div class="row"><strong>${r.reviewer}</strong><span class="pill">${r.verdict.replace("_", " ")}</span><span class="faint">#${r.round}</span></div>
          <${RichText} text=${r.findings} class="prose muted" style="margin-top:6px" /></div>`)}</div>` : null}
      ${pending.length ? html`<div class="section"><div class="label">${t("comments")}</div>
        ${pending.map((c) => html`<div class="card" style="margin-bottom:8px"><strong>${c.author}</strong>
          ${c.path ? html` <span class="faint mono">${c.path}${c.line ? `:${c.line}` : ""}</span>` : null}
          <${RichText} text=${c.body} class="prose muted" /></div>`)}</div>` : null}
      </div>` : null}
      ${shown === "summary" ? html`<div>
      <div class="section"><div class="label">${t("prompt")}</div><div class="card prose">${task.prompt}</div></div>
      ${d.plan && task.status === "planned" ? html`
        <div class="section"><div class="label">${t("plan_steps")}</div>
          ${d.plan.map((s, i) => html`<div class="card" style="margin-bottom:8px">
            <div class="row"><strong>${i + 1}. ${s.title || s.agent}</strong><span class="pill">${s.agent}</span></div>
            <${RichText} text=${s.prompt} class="prose muted" style="margin-top:6px" /></div>`)}
        </div>` : null}
      ${d.simulation && task.status === "planned" ? html`<div class="section"><div class="label">${t("simulation")}</div><div class="card">
        ${d.simulation.files.length ? html`<div><span class="faint">${t("sim_files")}:</span> <span class="mono">${d.simulation.files.map((f) => f.file).join(", ")}</span></div>` : null}
        <div><span class="faint">${t("sim_cost")}:</span> ${d.simulation.cost.minutes != null ? `~${d.simulation.cost.minutes} min, ` : ""}${d.simulation.cost.calls}–${d.simulation.cost.calls_worst} ${t("calls_unit")}</div>
        ${d.simulation.risks.map((r) => html`<div style="color:var(--warn)">⚠ ${r}</div>`)}
        <div class="faint">${t("sim_waits")}: ${d.simulation.approvals.join("; ")}</div></div></div>` : null}
      ${task.summary ? html`<div class="section"><div class="label">${t("summary")}</div><${RichText} text=${task.summary} /></div>` : null}
      ${task.error ? html`<div class="section"><div class="label">${t("failed")}</div><div class="card prose" style="color:var(--danger)">${task.error}</div></div>` : null}
      ${d.council ? html`<div class="section"><div class="label">${t("council_answers")}</div>
        ${d.council.map((a) => html`<div class="card" style="margin-bottom:8px">
          <div class="row"><strong>${a.agent}</strong>${a.success ? null : html`<${Pill} status="failed" />`}</div>
          <${RichText} text=${a.answer} class="prose muted" /></div>`)}</div>` : null}
      ${d.howto?.status === "proposed" ? html`<div class="section"><div class="label">${t("howto")}</div>
        <div class="card"><strong>${d.howto.title}</strong> <span class="faint">${d.howto.when}</span>
          <${RichText} text=${d.howto.steps} class="prose muted" style="margin-top:6px" />
          <div class="row" style="margin-top:8px"><button class="btn primary" disabled=${busy} onClick=${() => act("howto-accept")}>${t("keep")}</button></div></div></div>` : null}
      ${blockers.length && !["merged", "discarded"].includes(task.status) ? html`<div class="section"><div class="label" style="color:${d.override ? "var(--text-muted)" : "var(--warn)"}">${d.override ? `${t("overridden")}: ${d.override}` : `⚠ ${t("blocked")}`}</div></div>` : null}
      ${d.violations?.length ? html`<div class="section"><div class="label">${t("violations")}</div>
        ${d.violations.map((v) => html`<div class="card" style="margin-bottom:8px"><strong>${v.rule}</strong><div class="faint">${v.where} · ${v.by}</div></div>`)}</div>` : null}
      ${d.verification?.checks?.length ? html`<div class="section"><div class="label">${t("verification")}: ${d.verification.held}/${d.verification.total}</div>
        ${d.verification.checks.map((c) => html`<div class="card" style="margin-bottom:8px"><div class="row"><${Pill} status=${c.held ? "done" : "failed"} label=${c.held ? t("check_held") : t("failed_check")} /><span>${c.assumption}</span></div>
          <div class="mono faint" style="margin-top:6px;word-break:break-all">$ ${c.check}</div></div>`)}</div>` : null}
      ${d.hypotheses?.length ? html`<div class="section"><div class="label">${t("hypotheses")}</div>
        ${d.hypotheses.map((h) => html`<div class="card" style="margin-bottom:8px"><div class="row"><${Pill} status=${h.result === "confirmed" ? "failed" : h.result === "ruled out" ? "done" : "planned"} label=${h.result} /><strong>${h.cause}</strong></div>
          <div class="faint">${h.where} · ${h.proposed_by.join(", ")}</div></div>`)}
        ${d.hypotheses.some((h) => h.result === "confirmed") ? html`<button class="btn primary" disabled=${busy} onClick=${() => act("fix-bug")}>${t("fix_bug")}</button>` : null}</div>` : null}
      ${d.incidents?.length ? html`<div class="section"><div class="label" style="color:var(--danger)">⚠ ${t("incidents")}</div>
        ${d.incidents.map((i) => html`<div class="card" style="margin-bottom:8px;border-color:var(--danger)">
          <div class="row"><${Pill} status=${i.severity === "high" ? "failed" : "waiting"} label=${i.severity} /><strong>${i.kind}</strong><span class="faint">${i.agent || ""}</span></div>
          <div class="mono faint" style="margin-top:6px;word-break:break-all">${i.detail}</div></div>`)}</div>` : null}
      ${d.retries?.length ? html`<div class="section"><div class="label">${t("retries")}</div>
        ${d.retries.map((r) => html`<div class="row faint">${r.kind === "tests" ? `tests → ${r.agent} (${r.round})` : `${r.agent} → ${r.next}: ${(r.error || "").slice(0, 120)}`}</div>`)}</div>` : null}
      ${d.steps ? html`<div class="section"><div class="label">${t("steps")}</div>
        ${d.steps.map((s) => html`<div class="row"><${Pill} status=${s.success ? "done" : "failed"} /> ${s.title} <span class="faint">${s.agent} · ${s.duration_s}s</span></div>`)}</div>` : null}
      ${d.learn?.some((f) => f.status === "proposed") ? html`<div class="section"><div class="label">${t("learn")}</div>
        ${d.learn.map((f, i) => f.status === "proposed" ? html`<div class="card row" style="margin-bottom:8px">
          <span style="flex:1">${f.fact}</span>
          <button class="btn primary" disabled=${busy} onClick=${() => act("learn", { accept: [i] })}>${t("remember")}</button>
          <button class="btn ghost" disabled=${busy} onClick=${() => act("learn", { reject: [i] })}>${t("forget")}</button></div>` : null)}</div>` : null}
      </div>` : null}
    </div>`;
}

export function TasksView({ loading, tasks, status, selected, select, toast, reload }) {
  useTick(30000);
  const [project, setProject] = useState("");
  const [state, setState] = useState("");
  const [query, setQuery] = useState("");
  const [composing, setComposing] = useState(false);
  const [listW, setListW, commitListW] = useSplitWidth(SPLIT_TASKS, 360, 260, 560);
  const words = query.trim().toLowerCase();
  const shown = tasks.filter((x) => (!project || x.project === project) && (!state || x.status === state)
    && (!words || `${x.prompt} ${x.id} ${x.branch || ""} ${x.agent}`.toLowerCase().includes(words)));
  const groups = [
    ["waiting_for_you", shown.filter(decisionOf)],
    ["working_now", shown.filter((x) => RUNNING.includes(x.status))],
    ["earlier", shown.filter((x) => !decisionOf(x) && !RUNNING.includes(x.status))],
  ].filter(([, list]) => list.length);
  const row = (x) => html`
    <button key=${x.id} class="task-row ${x.id === selected ? "active" : ""}" onClick=${() => select(x.id)}>
      <span class="task-title">${firstLine(x.prompt)}</span><${Pill} status=${x.status} />
      <span class="task-meta">${x.project} · ${x.agent} · ${x.status === "running" ? t("running_for", { time: ago(x.created_at) }) : ago(x.created_at)}${x.diffstat ? html` · <span class="tone-ok">+${x.diffstat.added}</span> <span class="tone-danger">−${x.diffstat.removed}</span>` : null}</span>
    </button>`;
  return html`
    <div class="split ${selected ? "has-selected" : ""}" style=${{ "--list-w": `${listW}px` }}>
      <div class="list">
        <div class="list-tools">
          <button class="btn new-task" aria-expanded=${composing} onClick=${() => setComposing(!composing)}>${composing ? t("hide") : `+ ${t("new_task")}`}</button>
          <input class="input" type="search" placeholder=${t("filter_tasks")} aria-label=${t("filter_tasks")} value=${query} onInput=${(e) => setQuery(e.target.value)} />
          <div class="row">
            <select class="chip-select" value=${project} onChange=${(e) => setProject(e.target.value)}>
              <option value="">${t("all_projects")}</option>
              ${(status?.projects || []).map((p) => html`<option value=${p.name}>${p.name}</option>`)}
            </select>
            <select class="chip-select" value=${state} onChange=${(e) => setState(e.target.value)}>
              <option value="">${t("all_statuses")}</option>
              ${STATUS_ORDER.map((st) => html`<option value=${st}>${tStatus(st)}</option>`)}
            </select>
          </div>
        </div>
        ${composing ? html`<${Composer} status=${status} toast=${toast} onCreated=${(task) => { reload(); select(task.id); setComposing(false); }} />` : null}
        ${groups.length ? groups.map(([key, list]) => html`<div class="list-group">${t(key)}</div>${list.map(row)}`)
          : html`<div class="empty">${loading ? t("loading") : t("no_tasks")}</div>`}
      </div>
      <${VSplitter} width=${listW} setWidth=${setListW} commit=${commitListW} min=${260} max=${560} def=${360} />
      ${selected ? html`<${TaskDetail} id=${selected} toast=${toast} onChanged=${reload} onBack=${() => select(null)} />`
        : html`<div class="empty">${t("pick_task")}</div>`}
    </div>`;
}

// What waits for the owner's decision. The rule lives in dia.core.taskstate: the API sends
// it as `decision` on every task (merge | plan | ci | comments), as it does for the widget.
export function decisionOf(task) {
  return task.decision || null;
}

export const RUNNING = ["running", "queued", "waiting"];
