import { useEffect, useRef, useState } from "preact/hooks";
import { html } from "../html.js";
import { api } from "../api.js";
import { t } from "../i18n.js";
import { Meter } from "../ui/charts.js";
import { Pill } from "../ui/icons.js";
import { SummaryRow } from "./status_summary.js";
import { confirmDialog, promptDialog } from "../ui/dialog.js";
import { Resource, useResource } from "../ui/resource.js";
import { DiaLogo } from "../ui/logo.js";
import { clock } from "../util.js";

export function SystemCard() {
  const res = useResource("/api/system", { interval: 5000 });
  return html`<${Resource} res=${res}>${(info) => html`
    <div class="label">${t("computer")}</div>
    <div class="grid section" style="margin-top:8px">
      <${Meter} label=${`CPU${info.cpu_temp != null ? ` · ${Math.round(info.cpu_temp)}°C` : ""}`} used=${info.cpu_percent} limit=${100} unit="%" />
      <${Meter} label=${`RAM · ${info.memory.used_gb}/${info.memory.total_gb} GB`} used=${info.memory.percent} limit=${100} unit="%" />
      ${info.disks.slice(0, 3).map((d) => html`<${Meter} label=${`${t("disk")} ${d.mount} · ${(d.total_gb - d.used_gb).toFixed(0)} GB ${t("free")}`} used=${d.percent} limit=${100} unit="%" />`)}
      ${info.battery ? html`<${Meter} label=${`${t("battery")} · ${info.battery.status}`} used=${info.battery.percent} limit=${100} unit="%" />` : null}
    </div>
    <div class="card section"><table class="table">
      <tr><th>${t("process")}</th><th>CPU</th><th>RAM</th><th>${t("user")}</th></tr>
      ${info.top.map((p) => html`<tr title=${p.command}><td>${p.name} <span class="faint">${p.pid}</span></td>
        <td>${p.cpu_percent}%</td><td>${Math.round(p.memory_mb)} MB</td><td class="faint">${p.user}</td></tr>`)}
    </table></div>`}<//>`;
}

export function SecurityCard({ toast }) {
  const [report, setReport] = useState(null);
  const [busy, setBusy] = useState(false);
  const check = async () => {
    setBusy(true);
    try { setReport(await api("/api/security")); } catch (e) { toast(e.message, "error"); }
    setBusy(false);
  };
  return html`
    <div class="label section">${t("security")}</div>
    <div class="card" style="margin-top:8px">
      ${report ? html`<pre class="prose" style="white-space:pre-wrap;margin:0">${report.text}</pre>
        ${report.listening.filter((s) => s.exposed).length ? html`<table class="table section">
          <tr><th>${t("port")}</th><th>${t("net_address")}</th><th>${t("process")}</th></tr>
          ${report.listening.filter((s) => s.exposed).map((s) => html`<tr><td>${s.port}</td><td class="mono">${s.address}</td><td>${s.process}</td></tr>`)}
        </table>` : null}` : html`<p class="muted">${t("security_help")}</p>`}
      <div class="row" style="margin-top:8px"><button class="btn" disabled=${busy} onClick=${check}>${busy ? "…" : t("security_check")}</button></div>
    </div>`;
}

export function TidyCard({ toast }) {
  const [plan, setPlan] = useState(null);
  const [busy, setBusy] = useState(false);
  const run = async (fn) => { setBusy(true); try { await fn(); } catch (e) { toast(e.message, "error"); } setBusy(false); };
  const preview = () => run(async () => setPlan(await api("/api/tidy")));
  const apply = () => run(async () => {
    const done = await api(`/api/tidy/${plan.id}/apply`, { method: "POST" });
    toast(t("tidy_done", { n: done.moved.length })); setPlan({ ...done, text: t("tidy_done", { n: done.moved.length }) });
  });
  const undo = () => run(async () => { await api(`/api/tidy/${plan.id}/undo`, { method: "POST" }); setPlan(null); });
  return html`
    <div class="label section">${t("tidy")}</div>
    <div class="card" style="margin-top:8px">
      ${plan ? html`<p>${plan.text}</p>
        ${plan.status === "proposed" ? html`<table class="table">${plan.moves.slice(0, 50).map((m) => html`<tr><td class="mono">${m.from}</td><td class="mono">→ ${m.to}</td></tr>`)}</table>` : null}`
        : html`<p class="muted">${t("tidy_help")}</p>`}
      <div class="row" style="margin-top:8px">
        <button class="btn" disabled=${busy} onClick=${preview}>${t("tidy_preview")}</button>
        ${plan?.status === "proposed" && plan.moves.length ? html`<button class="btn primary" disabled=${busy} onClick=${apply}>${t("tidy_apply")}</button>` : null}
        ${plan?.status === "applied" ? html`<button class="btn ghost" disabled=${busy} onClick=${undo}>${t("tidy_undo")}</button>` : null}
      </div>
    </div>`;
}

// An agent and, optionally, its model for this one job: sent as "agent:model".
export function AgentPick({ status, value, onChange }) {
  const [agent, model] = [value.split(":")[0], value.split(":").slice(1).join(":")];
  const info = (status?.agents || []).find((a) => a.name === agent);
  const id = `dl-pick-${useRef(Math.random().toString(36).slice(2)).current}`;
  return html`<span class="row">
    <select class="select" value=${agent} onChange=${(e) => onChange(e.target.value)}>
      <option value="">${t("default_agent")}</option>
      ${(status?.agents || []).map((a) => html`<option value=${a.name}>${a.name}</option>`)}</select>
    ${info ? html`<input class="input" style="width:130px" list=${id} placeholder=${`${t("model")}: ${info.model || t("auto")}`}
        value=${model} onInput=${(e) => onChange(e.target.value ? `${agent}:${e.target.value}` : agent)} />
      <datalist id=${id}>${info.models.map((m) => html`<option value=${m}></option>`)}</datalist>` : null}</span>`;
}

export function ExperimentCard({ status, toast }) {
  const [question, setQuestion] = useState("");
  const [approaches, setApproaches] = useState("");
  const [agents, setAgents] = useState("");
  const [project, setProject] = useState(status.projects[0]?.name || "");
  const start = async (e) => {
    e.preventDefault();
    if (!question.trim() || !project) return;
    const list = approaches.split("\n").map((a) => a.trim()).filter(Boolean);
    try {
      await api("/api/experiments", { method: "POST", body: { project, question, approaches: list, agents: agents.split(/[,\s]+/).filter(Boolean) } });
      toast(t("experiment_started")); setQuestion(""); setApproaches("");
    } catch (err) { toast(err.message, "error"); }
  };
  return html`
    <div class="label section">${t("experiment")}</div>
    <form class="card" style="margin:8px 0 16px" onSubmit=${start}>
      <p class="muted">${t("experiment_help")}</p>
      <textarea class="textarea" style="min-height:50px" placeholder=${t("experiment_question")} value=${question} onInput=${(e) => setQuestion(e.target.value)}></textarea>
      <textarea class="textarea" style="min-height:50px;margin-top:8px" placeholder=${t("experiment_approaches")} value=${approaches} onInput=${(e) => setApproaches(e.target.value)}></textarea>
      <div class="row" style="margin-top:8px">
        <select class="select" value=${project} onChange=${(e) => setProject(e.target.value)}>
          ${status.projects.map((p) => html`<option value=${p.name}>${p.name}</option>`)}</select>
        <input class="input" style="flex:1" list="agent-specs" placeholder=${t("agents_models_hint")} value=${agents} onInput=${(e) => setAgents(e.target.value)} />
        <button class="btn primary">${t("experiment_start")}</button></div>
    </form>`;
}

export function WorkCard({ toast }) {
  const res = useResource("/api/work");
  const [note, setNote] = useState("");
  const [text, setText] = useState("");
  const load = res.reload;
  const call = async (action, body) => {
    try { setText((await api(`/api/work/${action}`, { method: "POST", body })).text); setNote(""); load(); }
    catch (e) { toast(e.message, "error"); }
  };
  return html`<${Resource} res=${res}>${(data) => html`<div class="label section">${t("work")}</div><div class="card" style="margin:8px 0 16px">
    <div class="row">${Object.keys(data.profiles).map((name) => html`<button class="btn ${data.current === name ? "primary" : ""}" onClick=${() => call("start", { name })}>${t("work_start")}: ${name}</button>`)}</div>
    ${data.current ? html`<div class="row" style="margin-top:8px"><input class="input" style="flex:1" placeholder=${t("work_note")} value=${note} onInput=${(e) => setNote(e.target.value)} />
      <button class="btn" onClick=${() => call("stop", { note })}>${t("work_stop")}</button></div>` : null}
    ${text ? html`<pre class="prose" style="white-space:pre-wrap;margin-top:8px">${text}</pre>` : null}</div>`}<//>`;
}

export function SuggestionsCard({ toast }) {
  const res = useResource("/api/suggestions");
  const load = res.reload;
  const call = async (key, action) => {
    try { await api(`/api/suggestions/${encodeURIComponent(key)}/${action}`, { method: "POST" }); load(); }
    catch (e) { toast(e.message, "error"); }
  };
  return html`<${Resource} res=${res} quiet>${(items) => html`<div class="label">${t("suggestions")}</div>${items.map((s) => html`<div class="card row" style="margin:8px 0">
    <span style="flex:1">${s.text}</span>${s.action ? html`<button class="btn primary" onClick=${() => call(s.key, "accept")}>${t("accept")}</button>` : null}
    <button class="btn ghost" onClick=${() => call(s.key, "dismiss")}>${t("dismiss")}</button></div>`)}`}<//>`;
}

export function HealthCard() {
  const res = useResource("/api/health");
  const broken = (items) => Object.entries(items).filter(([, h]) => h.state === "restarting" || h.restarts);
  return html`<${Resource} res=${res} quiet empty=${(items) => !broken(items).length}>${(items) => html`<div class="label">${t("health")}</div>${broken(items).map(([name, h]) => html`<div class="card" style="margin:8px 0">
    <div class="row"><${Pill} status=${h.state === "restarting" ? "failed" : "done"} label=${h.state === "restarting" ? t("restarting") : h.state} /><strong>${name}</strong><span class="faint">${h.restarts}×</span></div>
    ${h.error ? html`<div class="mono faint">${h.error}</div>` : null}</div>`)}`}<//>`;
}

export function DebugCard({ status, toast }) {
  const [bug, setBug] = useState("");
  const [agents, setAgents] = useState("");
  const [project, setProject] = useState(status.projects[0]?.name || "");
  const start = async (e) => {
    e.preventDefault();
    if (!bug.trim() || !project) return;
    try { await api("/api/debug", { method: "POST", body: { project, bug, agents: agents.split(/[,\s]+/).filter(Boolean) } }); toast(t("debug_started")); setBug(""); }
    catch (err) { toast(err.message, "error"); }
  };
  return html`
    <div class="label section">${t("debug")}</div>
    <form class="card" style="margin:8px 0 16px" onSubmit=${start}>
      <p class="muted">${t("debug_help")}</p>
      <textarea class="textarea" style="min-height:50px" placeholder=${t("debug_placeholder")} value=${bug} onInput=${(e) => setBug(e.target.value)}></textarea>
      <div class="row" style="margin-top:8px">
        <select class="select" value=${project} onChange=${(e) => setProject(e.target.value)}>
          ${status.projects.map((p) => html`<option value=${p.name}>${p.name}</option>`)}</select>
        <input class="input" style="flex:1" list="agent-specs" placeholder=${t("agents_models_hint")} value=${agents} onInput=${(e) => setAgents(e.target.value)} />
        <button class="btn primary">${t("debug_start")}</button></div>
    </form>`;
}

export function benchmarkText(data) {
  if (!data.results.length) return t("no_benchmarks");
  return data.results.slice(0, 15).map((r) => `${r.at.slice(0, 16).replace("T", " ")}  ${r.sha.slice(0, 8)}  ${(r.ref || "-").padEnd(12)} `
    + Object.entries(r.metrics).map(([k, v]) => `${k}=${v}`).join("  ")).join("\n");
}

// Dia's CLI commands with their output (POST /api/tools): whatever has no button
// of its own still works from the app.
export const splitArgs = (line) => [...line.matchAll(/"([^"]*)"|'([^']*)'|(\S+)/g)].map((m) => m[1] ?? m[2] ?? m[3]);

export async function runTool(command, args = []) {
  const r = await api("/api/tools", { method: "POST", body: { command, args } });
  return r.output.replace(/^\s*\n/, "").trimEnd() || t(r.code ? "tool_failed" : "tool_done");
}

export const TOOL_BUTTONS = [
  ["tool_doctor", "doctor", []], ["tool_doctor_fix", "doctor", ["--fix"]],
  ["tool_sandbox", "sandbox", ["check"]], ["tool_limits", "limits", []],
  ["tool_issues", "issues", []], ["tool_agents", "agents", []], ["tool_redteam", "redteam", []],
];

export function ToolsCard({ toast }) {
  const [out, setOut] = useState("");
  const [busy, setBusy] = useState("");
  const [line, setLine] = useState("");
  const run = async (command, args) => {
    if (command === "redteam" && !(await confirmDialog(t("redteam_confirm"), { danger: true }))) return;
    setBusy(command); setOut("");
    try { setOut(await runTool(command, args)); } catch (e) { toast(e.message, "error"); }
    setBusy("");
  };
  const custom = (e) => {
    e.preventDefault();
    const words = splitArgs(line.replace(/^\s*dia\s+/, ""));
    if (words.length) run(words[0], words.slice(1));
  };
  return html`<div class="label section">${t("tools")}</div>
    <div class="card" style="margin:8px 0 16px">
      <p class="muted">${t("tools_help")}</p>
      <div class="row">${TOOL_BUTTONS.map(([key, command, args]) => html`
        <button class="btn ghost" disabled=${!!busy} onClick=${() => run(command, args)}>${t(key)}</button>`)}</div>
      <form class="row" style="margin-top:8px" onSubmit=${custom}><span class="mono faint">dia</span>
        <input class="input mono" style="flex:1" placeholder=${t("tool_placeholder")} value=${line} onInput=${(e) => setLine(e.target.value)} />
        <button class="btn" disabled=${!!busy || !line.trim()}>${t("tool_run")}</button></form>
      ${busy ? html`<p class="muted">${t("tool_running", { name: busy })}</p>` : null}
      ${out ? html`<pre class="mono" style="white-space:pre-wrap;margin-top:8px;max-height:420px;overflow:auto">${out}</pre>` : null}
    </div>`;
}

export function SkillsCard({ toast }) {
  const [skills, setSkills] = useState([]);
  const [name, setName] = useState("");
  const [args, setArgs] = useState({});
  const [out, setOut] = useState("");
  const [busy, setBusy] = useState(false);
  const res = useResource("/api/skills", { on: (list) => { setSkills(list); setName((n) => n || list[0]?.name || ""); } });
  const skill = skills.find((s) => s.name === name);
  const run = async (e, yes = false) => {
    if (e) e.preventDefault();
    setBusy(true);
    try {
      const r = await api(`/api/skills/${name}`, { method: "POST", body: { args, confirm: yes } });
      if (r.question) {
        setBusy(false);
        if (await confirmDialog(r.question)) run(null, true);
        return;
      }
      setOut(r.text);
    } catch (err) { toast(err.message, "error"); }
    setBusy(false);
  };
  if (!skills.length) return html`<${Resource} res=${res} quiet>${() => null}<//>`;
  return html`<div class="label section">${t("skills")}</div>
    <form class="card" style="margin:8px 0 16px" onSubmit=${run}>
      <div class="row">
        <select class="select" value=${name} onChange=${(e) => { setName(e.target.value); setArgs({}); setOut(""); }}>
          ${skills.map((s) => html`<option value=${s.name}>${s.name}</option>`)}</select>
        <span class="muted" style="flex:1">${skill?.description}</span></div>
      ${Object.entries(skill?.args || {}).map(([key, help]) => html`<label class="field" style="margin-top:8px"><span>${key} <span class="faint">${help}</span></span>
        <input class="input" value=${args[key] || ""} onInput=${(e) => setArgs({ ...args, [key]: e.target.value })} /></label>`)}
      <div class="row" style="margin-top:8px"><button class="btn primary" disabled=${busy}>${busy ? "…" : t("skill_run")}</button></div>
      ${out ? html`<pre class="prose" style="white-space:pre-wrap;margin-top:8px">${out}</pre>` : null}
    </form>`;
}

export function HeldCard() {
  const res = useResource("/api/notifications");
  return html`<${Resource} res=${res} quiet empty=${(data) => !data?.held?.length}>${(data) => html`<div class="label">${t("held_notes")} (${data.held.length})</div>
    <div class="card" style="margin:8px 0 16px">${data.held.map((h) => html`<div style="margin-bottom:6px">
      <span class="faint mono">${clock(h.at)}</span> <strong>${h.title}</strong> <span class="muted">${h.body}</span></div>`)}</div>`}<//>`;
}

export function AboutCard() {
  const res = useResource("/api/about");
  return html`<${Resource} res=${res} empty=${(about) => !about?.version}>${(about) => html`<${AboutBody} about=${about} />`}<//>`;
}

function AboutBody({ about }) {
  const link = (href, label) => html`<a href=${href} target="_blank" rel="noreferrer">${label}</a>`;
  return html`<div class="about-card">
    <div class="about-head">
      <${DiaLogo} class="about-logo" />
      <div>
        <h2>Dia ${about.version}</h2>
        <p class="muted">${t("about_tagline")}</p>
      </div>
    </div>
    <div class="kv card">
      <span>${t("about_author")}</span><span>${about.author}</span>
      <span>${t("about_website")}</span><span>${link(about.website, about.website.replace(/^https:\/\//, ""))}</span>
      <span>${t("about_github")}</span><span>${link(about.github, about.github.replace(/^https:\/\//, ""))}</span>
      <span>${t("about_email")}</span><span>${link(`mailto:${about.email}`, about.email)}</span>
      <span>${t("about_license")}</span><span>${link(about.license_url, about.license)}</span>
      ${about.config ? html`<span>${t("about_config")}</span><span class="mono faint">${about.config}</span>` : null}
      ${about.data_dir ? html`<span>${t("about_data")}</span><span class="mono faint">${about.data_dir}</span>` : null}
    </div>
    <div class="label">${t("about_components")}</div>
    <div class="table-wrap">
      <table class="about-table">
        ${(about.components || []).map((row) => html`<tr>
          <td>${row.name}</td>
          <td>${row.version}</td>
          <td class="faint">${row.detail || ""}</td></tr>`)}
      </table>
    </div>
  </div>`;
}

export function StatusView({ status, reload, toast }) {
  const [analysis, setAnalysis] = useState({});
  if (!status) return html`<div class="state loading" role="status">${t("loading")}</div>`;
  const analyze = async (project, kind = "analysis") => {
    try {
      const a = await api(`/api/projects/${project}/${kind}`);
      setAnalysis({ ...analysis, [project]: kind === "benchmarks" ? benchmarkText(a) : a.text });
    }
    catch (e) { toast(e.message, "error"); }
  };
  const impactOf = async (project, q) => {
    try { const a = await api(`/api/projects/${project}/impact?q=${encodeURIComponent(q)}`); setAnalysis({ ...analysis, [project]: a.text }); }
    catch (e) { toast(e.message, "error"); }
  };
  const fixDebt = async (project, n) => {
    if (!n) return;
    try { await api(`/api/projects/${project}/debt/${n}/fix`, { method: "POST" }); toast(t("debt_fixing")); }
    catch (e) { toast(e.message, "error"); }
  };
  const checkNotes = async (project) => {
    try { await api(`/api/projects/${project}/contradictions`, { method: "POST" }); toast(t("check_started")); }
    catch (e) { toast(e.message, "error"); }
  };
  const build = async (project) => {
    try { await api("/api/builds", { method: "POST", body: { project, write_changelog: true } }); toast(t("build_started")); }
    catch (e) { toast(e.message, "error"); }
  };
  const tool = async (project, command, args) => {
    setAnalysis({ ...analysis, [project]: t("tool_running", { name: command }) });
    try { const out = await runTool(command, args); setAnalysis((all) => ({ ...all, [project]: out })); }
    catch (e) { setAnalysis((all) => ({ ...all, [project]: "" })); toast(e.message, "error"); }
  };
  const jump = (id) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  const jumps = [
    ["status-now", "status_now"], ["status-computer", "status_computer"],
    ["status-agents", "agents"], ["status-projects", "projects"],
    ["status-work", "status_work"], ["status-about", "status_about"],
  ];
  return html`
    <div class="page wide status">
      <div class="page-head">
        <h1>${t("status")}</h1>
        <p class="muted">${t("version")}: Dia ${status.version || "?"}</p>
      </div>
      <${SummaryRow} status=${status} />
      <div class="page-jump" role="navigation" aria-label=${t("jump_to")}>
        ${jumps.map(([id, key]) => html`<button type="button" class="jump-chip" onClick=${() => jump(id)}>${t(key)}</button>`)}
        <span class="spacer"></span>
        <button class="btn" onClick=${reload}>${t("refresh")}</button>
      </div>
      <div class="status-board">
        <section id="status-now" class="status-section">
          <${SuggestionsCard} toast=${toast} />
          <${HealthCard} />
          <${WorkCard} toast=${toast} />
          <${HeldCard} />
        </section>
        <section id="status-computer" class="status-section">
          <${SystemCard} />
          <${SecurityCard} toast=${toast} />
          <${TidyCard} toast=${toast} />
        </section>
        <section id="status-agents" class="status-section">
          <div class="label">${t("agents")}</div>
          <div class="grid" style="margin-top:8px">
            ${status.agents.map((a) => html`<div class="card">
              <div class="stat-title">${a.name}${a.limited_until
                ? html`<${Pill} status="limited" label=${t("limited")} />`
                : html`<${Pill} status=${a.ok ? "done" : "failed"} label=${a.ok ? "ok" : t("failed")} />`}</div>
              <div class="muted">${a.type}${a.role ? ` · ${a.role}` : ""} · ${t("model_label")}: ${a.model || t("auto")}</div>
              ${a.limited_until ? html`<div style="color:var(--warn);margin-top:6px">${t("limited_until", { time: clock(a.limited_until) })}
                ${status.device && !status.device_full ? null : html` <button class="btn ghost" onClick=${() => runTool("limits", ["--clear", a.name]).then(reload).catch((e) => toast(e.message, "error"))}>${t("clear_limit")}</button>`}</div>` : null}
              ${a.problem ? html`<div style="color:var(--danger);margin-top:6px">${a.problem}</div>` : null}</div>`)}
          </div>
          <datalist id="agent-specs">${status.agents.flatMap((a) => [a.name, ...a.models.map((m) => `${a.name}:${m}`)]).map((o) => html`<option value=${o}></option>`)}</datalist>
        </section>
        <section id="status-projects" class="status-section">
          <div class="label">${t("projects")}</div>
          <div class="grid" style="margin-top:8px">
            ${status.projects.map((p) => html`<div class="card">
              <div class="stat-title">${p.name}<${Pill} status=${p.ok ? "done" : "failed"} label=${p.ok ? "ok" : t("failed")} /></div>
              <div class="muted mono" style="word-break:break-all">${p.path}</div>
              ${p.toolchain ? html`<div class="faint">${p.toolchain}</div>` : null}
              ${p.presets?.length ? html`<div class="row" style="margin-top:8px">
                <button class="btn" onClick=${() => build(p.name)}>${t("build")}</button>
                <span class="faint">${p.presets.join(", ")}</span></div>` : null}
              ${p.toolchain?.startsWith("godot") ? html`<div class="row" style="margin-top:8px">
                <button class="btn ghost" onClick=${() => analyze(p.name)}>${t("analyze")}</button>
                <button class="btn ghost" onClick=${() => analyze(p.name, "balance")}>${t("balance")}</button></div>` : null}
              <form class="row" style="margin-top:8px" onSubmit=${(e) => { e.preventDefault(); const q = e.target.elements.q.value.trim(); if (q) impactOf(p.name, q); }}>
                <input class="input" name="q" style="flex:1" placeholder=${t("impact_placeholder")} />
                <button class="btn ghost">${t("impact")}</button></form>
              <div class="row" style="margin-top:8px"><button class="btn ghost" onClick=${() => checkNotes(p.name)}>${t("check_notes")}</button>
                <button class="btn ghost" onClick=${() => analyze(p.name, "debt?refresh=1")}>${t("debt")}</button></div>
              ${(analysis[p.name] || "").match(/^\s*\d+\. \[/) ? html`<form class="row" style="margin-top:8px" onSubmit=${(e) => { e.preventDefault(); fixDebt(p.name, e.target.elements.n.value); }}>
                <input class="input" name="n" type="number" min="1" style="width:80px" placeholder="#" /><button class="btn">${t("debt_fix")}</button></form>` : null}
              ${p.benchmark ? html`<div class="row" style="margin-top:8px">
                <button class="btn ghost" onClick=${() => analyze(p.name, "benchmarks")}>${t("benchmarks")}</button>
                ${status.device && !status.device_full ? null : html`<button class="btn ghost" onClick=${() => tool(p.name, "bench", [p.name])}>${t("bench_now")}</button>`}</div>` : null}
              ${status.device && !status.device_full ? null : html`<div class="row" style="margin-top:8px">
                <button class="btn ghost" onClick=${() => tool(p.name, "launch", [p.name])}>${t("launch")}</button>
                <button class="btn ghost" onClick=${() => tool(p.name, "check", [p.name])}>${t("check_now")}</button></div>
              <form class="row" style="margin-top:8px" onSubmit=${(e) => { e.preventDefault(); const c = e.target.elements.c.value.trim(); if (c) tool(p.name, "lab", [p.name, c]); }}>
                <input class="input mono" name="c" style="flex:1" placeholder=${t("lab_placeholder")} />
                <button class="btn ghost">${t("lab")}</button></form>`}
              ${analysis[p.name] ? html`<pre class="prose status-out">${analysis[p.name]}</pre>` : null}</div>`)}
          </div>
        </section>
        <section id="status-work" class="status-section">
          ${status.projects.length ? html`<${ExperimentCard} status=${status} toast=${toast} />` : null}
          ${status.projects.length ? html`<${DebugCard} status=${status} toast=${toast} />` : null}
          <${SkillsCard} toast=${toast} />
          ${status.device && !status.device_full ? null : html`<${ToolsCard} toast=${toast} />`}
        </section>
        <section id="status-about" class="status-section">
          <${AboutCard} />
          <div class="label" style="margin-top:16px">${t("about_instance")}</div>
          <div class="kv card" style="margin-top:8px">
            <span>${t("brains")}</span><span>${status.brains.join(" → ")}</span>
            <span>${t("memory")}</span><span>${status.memory || t("off")}</span>
            <span>${t("sandbox")}</span><span style=${status.sandbox === "on" ? "" : "color:var(--danger)"}>${t(`sandbox_${status.sandbox || "unavailable"}`)}</span>
            <span>${t("channels")}</span><span>${status.channels.join(", ") || "-"}</span>
            <span>${t("language")}</span><span>${status.language}</span>
          </div>
        </section>
      </div>
    </div>`;
}
