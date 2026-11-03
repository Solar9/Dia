import { useEffect, useState } from "preact/hooks";
import { html } from "../html.js";
import { api } from "../api.js";
import { t } from "../i18n.js";
import { LANGUAGE_NAMES } from "../lang/index.js";
import { confirmDialog, promptDialog } from "../ui/dialog.js";
import { runTool } from "./status.js";

// Settings forms: each field is [path in the config, label key, type, options].
// Saved to settings.json (laid over the config file), applied without a restart
// except where noted.
export const getPath = (obj, path) => path.split(".").reduce((o, k) => (o == null ? undefined : o[k]), obj);

export function setPath(obj, path, value) {
  const keys = path.split(".");
  let o = obj;
  keys.slice(0, -1).forEach((k) => { o = o[k] = o[k] && typeof o[k] === "object" ? o[k] : {}; });
  o[keys[keys.length - 1]] = value;
}

export const ruleLine = (r) => `${r.project ? `${r.project}:` : ""}${r.match} => ${r.agent}`;

export const parseRule = (line) => {
  const m = line.trim().match(/^(?:([\w-]+):)?(.+?)\s*=>\s*([\w.:-]+)$/);
  return m ? { ...(m[1] ? { project: m[1] } : {}), match: m[2].trim(), agent: m[3] } : null;
};

export const toForm = (value, type) => {
  if (type === "bool") return Boolean(value);
  if (type === "list") return (value || []).join(", ");
  if (type === "lines") return (value || []).join("\n");
  if (type === "rules") return (value || []).map(ruleLine).join("\n");
  return value == null ? "" : String(value);
};

export const fromForm = (value, type) => {
  if (type === "bool") return value;
  if (value === "") return null; // removed from the settings: the config file's value applies
  if (type === "number") return Number(value);
  if (type === "list") return value.split(/[,\s]+/).filter(Boolean);
  if (type === "lines") return value.split("\n").map((x) => x.trim()).filter(Boolean);
  if (type === "rules") return value.split("\n").map(parseRule).filter(Boolean);
  return value;
};

export function settingsForms(meta) {
  const v = meta.values;
  const forms = {
    assistant: [
      { section: "s_identity" },
      ["assistant.name", "f_name", "text"],
      ["assistant.user_name", "f_user_name", "text"],
      ["assistant.personality", "f_personality", "personality"],
      ["dia.language", "language", "select", Object.keys(LANGUAGE_NAMES)],
      { section: "s_skills_brief" },
      ["skills.weather.place", "f_weather_place", "text"],
      ["skills.news.feeds", "f_news_feeds", "lines"],
      ["skills.stocks.symbols", "f_stocks", "list"],
      ["skills.stocks.source", "f_stocks_source", "select", ["", "yahoo", "stooq"]],
      ["skills.crypto.coins", "f_crypto", "list"],
      ["skills.crypto.currency", "f_crypto_currency", "select", ["", "usd", "pln", "eur"]],
      ["skills.briefing.sections", "f_briefing", "list"],
      ["assistant.skills", "f_skills", "list"],
      { section: "s_conversation" },
      ["assistant.learn_preferences", "f_learn_prefs", "bool"],
      ["assistant.history_turns", "f_history_turns", "number"],
      ["assistant.history_minutes", "f_history_minutes", "number"],
      ["assistant.one_conversation", "f_one_conversation", "bool", null, false, true],
      ["assistant.owner_ids", "f_owner_ids", "list"],
      ["assistant.log_intents", "f_log_intents", "bool", null, false, true],
      { section: "s_chat_models" },
      ["chat.default", "f_chat_default", "text"],
      ["chat.ollama_url", "f_chat_ollama", "text"],
      ["chat.timeout", "f_chat_timeout", "number"],
    ],
    agents: [
      { section: "s_defaults" },
      ["dia.default_agent", "default_agent", "select", ["", ...meta.agents]],
      ["dia.max_parallel_tasks", "f_parallel", "number"],
      ["routing.auto", "f_routing_auto", "bool"],
      ["routing.min_tasks", "f_routing_min", "number"],
      ["routing.rules", "f_routing_rules", "rules"],
      ["limits.fallback", "f_fallback", "list"],
      ["limits.wait", "f_limit_wait", "bool"],
      ["limits.max_wait_hours", "f_max_wait", "number"],
      ["limits.cooldown_minutes", "f_cooldown", "number"],
      { section: "s_review_retry" },
      ["review.auto", "f_auto_review", "bool"],
      ["review.reviewer", "f_reviewer", "select", ["", ...meta.agents]],
      ["review.fix_rounds", "f_fix_rounds", "number"],
      ["review.max_diff_chars", "f_max_diff", "number"],
      ["retry.agent_errors", "f_retry_errors", "number"],
      ["retry.switch_agent", "f_retry_switch", "bool"],
      ["retry.test_fixes", "f_retry_tests", "number"],
      { section: "s_task_limits" },
      ["task_limits.minutes", "f_task_minutes", "number"],
      ["task_limits.calls", "f_task_calls", "number"],
      ["task_limits.agent_timeout", "f_agent_timeout", "number"],
      ["task_limits.nice", "f_nice", "number"],
      { section: "s_plans_missions" },
      ["plans.planner", "f_planner", "select", ["", ...meta.agents]],
      ["plans.max_steps", "f_plan_steps", "number"],
      ["missions.planner", "f_mission_planner", "select", ["", ...meta.agents]],
      ["missions.max_steps", "f_mission_steps", "number"],
      ["missions.budget_calls", "f_mission_calls", "number"],
      ["missions.budget_minutes", "f_mission_minutes", "number"],
      ["missions.step_tests", "f_mission_tests", "bool", null, false, true],
      { section: "s_specialists" },
      ["council.members", "f_council_members", "list"],
      ["council.moderator", "f_council_moderator", "select", ["", ...meta.agents]],
      ["experiments.agents", "f_experiment_agents", "list"],
      ["experiments.max_variants", "f_experiment_variants", "number"],
      ["debug.agents", "f_debug_agents", "list"],
      ["debug.max_checks", "f_debug_checks", "number"],
      ["profile.agent", "f_profile_agent", "select", ["", ...meta.agents]],
      ["contradictions.agent", "f_contradictions_agent", "select", ["", ...meta.agents]],
      ["research.agent", "f_research_agent", "select", ["", ...meta.agents]],
      { section: "s_quality" },
      ["verification.min_lines", "f_verify_lines", "number"],
      ["verification.always", "f_verify_always", "bool"],
      ["debt.function_lines", "f_debt_function", "number"],
      ["debt.nesting", "f_debt_nesting", "number"],
      ["debt.file_lines", "f_debt_file", "number"],
    ],
    automation: [
      { section: "s_watchers" },
      ["watch.enabled", "f_watch", "bool", null, true],
      ["watch.interval", "f_watch_interval", "number", null, true],
      ["watch.projects", "f_watch_projects", "list", null, true],
      ["watch.branch", "f_watch_branch", "text", null, true],
      ["issues.enabled", "f_issues", "bool", null, true],
      ["issues.label", "f_issues_label", "text", null, true],
      ["issues.interval", "f_issues_interval", "number", null, true],
      ["issues.planner", "f_issues_planner", "bool"],
      ["ci.autofix", "f_ci_autofix", "bool"],
      ["ci.watch", "f_ci_watch", "bool", null, false, true],
      ["ci.interval", "f_ci_interval", "number"],
      ["ci.fix_rounds", "f_ci_fix_rounds", "number"],
      ["ci.watch_comments", "f_ci_comments", "bool"],
      ["ci.autofix_comments", "f_ci_autofix_comments", "bool"],
      { section: "s_suggestions" },
      ["suggestions.per_day", "f_suggest_per_day", "number"],
      ["suggestions.repeat_days", "f_suggest_repeat", "number"],
      ["goals.review_days", "f_goal_days", "number"],
    ],
    integrations: [
      { section: "s_mail_home" },
      ["skills.mail.host", "f_mail_host", "text"],
      ["skills.mail.user", "f_mail_user", "text"],
      ["skills.home.url", "f_home_url", "text"],
      ["skills.notion.parent", "f_notion_parent", "text"],
      { section: "s_senses" },
      ["camera.device", "f_camera_device", "text"],
      ["screen.agent", "f_screen_agent", "select", ["", ...meta.agents]],
      { section: "s_publish" },
      ["builds.itch", "f_itch", "text"],
      ["builds.steam.app_id", "f_steam_app", "number"],
      ["builds.steam.username", "f_steam_user", "text"],
      ["builds.steam.branch", "f_steam_branch", "text"],
      ["builds.presets", "f_presets", "list"],
    ],
    security: [
      { section: "s_security_hosts" },
      ["security.hosts", "f_security_hosts", "list"],
      ["security.networks", "f_networks", "list"],
      { section: "s_sandbox" },
      ["sandbox.enabled", "f_sandbox", "select", ["", "auto", "true", "false"]],
      ["sandbox.decoys", "f_sandbox_decoys", "bool"],
      ["sandbox.allow_read", "f_sandbox_read", "list"],
    ],
    computer: [
      { section: "s_computer_alerts" },
      ["system.cpu_temp", "f_cpu_temp", "number"],
      ["system.disk_used", "f_disk_used", "number"],
      ["system.battery_low", "f_battery_low", "number"],
      ["system.check_urls", "f_check_urls", "lines"],
      { section: "s_tidy" },
      ["tidy.folders", "f_tidy_folders", "list"],
      { section: "s_lab" },
      ["lab.engine", "f_lab_engine", "select", ["", "podman", "docker"]],
      { section: "s_godot" },
      ["godot_analysis.max_nodes", "f_ga_nodes", "number"],
      ["godot_analysis.max_depth", "f_ga_depth", "number"],
      ["godot_analysis.max_lights", "f_ga_lights", "number"],
      ["godot_analysis.max_texture", "f_ga_texture", "number"],
    ],
    notify: [
      { section: "s_notify_policy" },
      ["push.events", "f_push_events", "list"],
      ["push.subject", "f_push_subject", "text"],
      ["notifications.quiet_hours", "f_quiet_hours", "text"],
      ["notifications.budget", "f_budget", "number"],
    ],
  };
  forms.memory = [
    { section: "s_vault" },
    ["memory.type", "f_memory_type", "select", ["", "obsidian", "markdown"]],
    ["memory.vault", "f_vault", "text"],
    ["memory.folder", "f_memory_folder", "text"],
    ["memory.projects_dir", "f_projects_dir", "text"],
    ["memory.journal_dir", "f_journal_dir", "text"],
    ["memory.profile_note", "f_profile_note", "text"],
    ["memory.exclude", "f_memory_exclude", "list"],
    ["memory.howtos_dir", "f_howtos_dir", "text"],
    ["memory.create_project_notes", "f_create_notes", "bool", null, false, true],
    ["memory.journal", "f_journal_on", "bool", null, false, true],
    { section: "s_memory_search" },
    ["memory.snippet_chars", "f_snippet_chars", "number"],
    ["memory.howto_results", "f_howto_results", "number"],
    ["memory.index_per_search", "f_index_per_search", "number"],
    ["memory.max_context_chars", "f_context_chars", "number"],
    ["memory.search_results", "f_search_results", "number"],
    ["memory.learn_agent", "f_learn_agent", "select", ["", ...meta.agents]],
  ];
  forms.remote = [
    ["ui.remote", "f_ui_remote", "bool", null, true],
    ["ui.public_url", "f_public_url", "text", null, true],
    ["ui.hosts", "f_ui_hosts", "list", null, true],
  ];
  if (v.channels?.discord) {
    forms.discord = [
      ["channels.discord.allowed_users", "f_discord_users", "list", null, true],
      ["channels.discord.guild_id", "f_discord_guild", "text", null, true],
      ["channels.discord.notify_channel_id", "f_discord_notify", "text", null, true],
    ];
  }
  forms.app = [
    ["app.tray", "f_app_tray", "bool", null, false, true],
    ["app.minimize_to_tray", "f_app_minimize", "bool", null, false, true],
    ["app.close_to_tray", "f_app_close", "bool", null, false, true],
    ["app.custom_titlebar", "f_app_titlebar", "bool", null, false, true],
    ["app.check_updates", "f_check_updates", "bool", null, false, true],
    ["ui.enabled", "f_ui_enabled", "bool", null, true, true],
    ["ui.port", "f_ui_port", "number", null, true],
  ];
  if (v.memory) {
    forms.memory.push(
      ["memory.learn", "f_learn", "bool"],
      ["memory.learn_model", "f_learn_model", "text"],
      ["memory.search", "f_memory_search", "select", ["", "folder", "vault", "off"]],
      ["memory.semantic.model", "f_semantic", "text"],
    );
  }
  if (v.channels?.voice) {
    const engine = getPath(v, "channels.voice.tts.type") || "piper";
    forms.voice = [
      ["channels.voice.language", "f_voice_language", "select", ["", "pl", "en"], true],
      ["channels.voice.stt.model", "f_stt_model", "text", null, true],
      ["channels.voice.tts.type", "f_tts", "select", meta.tts, true],
      ...(engine === "elevenlabs" ? [
        ["channels.voice.tts.voice_id", "f_voice_id", "text", null, true],
        ["channels.voice.tts.model", "f_eleven_model", "text", null, true],
        ["channels.voice.tts.stability", "f_stability", "number", null, true],
        ["channels.voice.tts.similarity_boost", "f_similarity", "number", null, true],
        ["channels.voice.tts.fallback", "f_tts_fallback", "select", ["", "piper"], true],
      ] : [["channels.voice.tts.voice", "f_piper_voice", "text", null, true]]),
      ["channels.voice.wake.model", "f_wake", "text", null, true],
      ["channels.voice.speaker.model", "f_speaker_model", "text", null, true],
      ["channels.voice.speaker.unknown", "f_speaker_unknown", "select", ["", "limited", "ignore", "allow"], true],
    ];
  }
  return forms;
}

export function Form({ fields, meta, onSaved, toast }) {
  // A field's sixth element is its default, shown when the config leaves it out.
  // { section: "key" } entries are headings, not fields.
  const entries = fields.filter((f) => Array.isArray(f));
  const initial = Object.fromEntries(entries.map(([path, , type, , , fallback]) => [path, toForm(getPath(meta.values, path) ?? fallback, type)]));
  const [form, setForm] = useState(initial);
  const [custom, setCustom] = useState(false);
  useEffect(() => setForm(initial), [meta]);
  const set = (path, value) => setForm({ ...form, [path]: value });
  const save = async () => {
    const changes = {};
    for (const [path, , type] of entries) {
      if (form[path] !== initial[path]) setPath(changes, path, fromForm(form[path], type));
    }
    if (!Object.keys(changes).length) return;
    try {
      const result = await api("/api/settings", { method: "PUT", body: { changes } });
      toast(result.restart_required.length ? t("saved_restart") : t("saved"));
      onSaved();
    } catch (e) { toast(e.message, "error"); }
  };
  const input = ([path, , type, options]) => {
    const value = form[path];
    if (type === "bool") return html`<input type="checkbox" checked=${value} onChange=${(e) => set(path, e.target.checked)} />`;
    if (type === "select") return html`<select class="select" value=${value} onChange=${(e) => set(path, e.target.value)}>
      ${options.map((o) => html`<option value=${o}>${LANGUAGE_NAMES[o] && path === "dia.language" ? LANGUAGE_NAMES[o] : o || "–"}</option>`)}</select>`;
    if (type === "combo") {
      const id = `dl-${path.replace(/\W/g, "-")}`;
      return html`<span><input class="input" list=${id} placeholder=${t("auto")} value=${value ?? ""} onInput=${(e) => set(path, e.target.value)} />
        <datalist id=${id}>${options.map((o) => html`<option value=${o}></option>`)}</datalist></span>`;
    }
    if (type === "lines" || type === "rules") return html`<textarea class="textarea" rows="3" value=${value} onInput=${(e) => set(path, e.target.value)}></textarea>`;
    if (type === "personality") {
      const preset = meta.personalities.includes(value) || value === "";
      return html`<div class="stack">
        <select class="select" value=${preset && !custom ? value : "__custom"} onChange=${(e) => {
          if (e.target.value === "__custom") { setCustom(true); set(path, preset ? "" : value); } else { setCustom(false); set(path, e.target.value); }
        }}>${["", ...meta.personalities].map((o) => html`<option value=${o}>${o ? t(`p_${o}`) : "–"}</option>`)}
          <option value="__custom">${t("p_custom")}</option></select>
        ${!preset || custom ? html`<textarea class="textarea" rows="3" placeholder=${t("p_custom_hint")} value=${value} onInput=${(e) => set(path, e.target.value)}></textarea>` : null}
      </div>`;
    }
    return html`<input class="input" type=${type === "number" ? "number" : "text"} step="any" value=${value} onInput=${(e) => set(path, e.target.value)} />`;
  };
  const fieldClass = (type) => type === "bool" ? "field field-bool" : type === "number" ? "field field-num" : "field";
  return html`<div class="card form">
    ${fields.map((field) => field.section
      ? html`<div class="form-section">${t(field.section)}</div>`
      : html`<label class=${fieldClass(field[2])}><span>${t(field[1])}${field[4] ? html` <span class="faint">↻</span>` : null}</span>${input(field)}</label>`)}
    <div class="row form-actions"><button class="btn primary" onClick=${save}>${t("save")}</button>
      ${entries.some((f) => f[4]) ? html`<span class="faint">↻ ${t("needs_restart")}</span>` : null}</div>
  </div>`;
}

export function LocalBrain({ meta, onSaved, toast }) {
  const local = meta.values.brains?.local;
  const [on, setOn] = useState(Boolean(local));
  const [model, setModel] = useState(local?.model || "qwen3.5:4b");
  const save = async () => {
    const order = meta.values.dia?.default_agent ? ["rules", "local", "default-agent"] : ["rules", "local"];
    const changes = on
      ? { brains: { local: { type: "ollama", model } }, dia: { brain: order } }
      : { brains: { local: null }, dia: { brain: null } };
    try { await api("/api/settings", { method: "PUT", body: { changes } }); toast(t("saved")); onSaved(); }
    catch (e) { toast(e.message, "error"); }
  };
  return html`<div class="card form">
    <label class="field field-bool"><span>${t("f_local_brain")}</span><input type="checkbox" checked=${on} onChange=${(e) => setOn(e.target.checked)} /></label>
    ${on ? html`<label class="field"><span>${t("f_ollama_model")}</span><input class="input" value=${model} onInput=${(e) => setModel(e.target.value)} /></label>` : null}
    <p class="muted">${t("local_brain_help")}</p>
    <div class="row"><button class="btn primary" onClick=${save}>${t("save")}</button></div>
  </div>`;
}

export function Secrets({ toast }) {
  const [items, setItems] = useState([]);
  const [values, setValues] = useState({});
  const [name, setName] = useState("");
  const load = () => api("/api/secrets").then(setItems).catch((e) => toast(e.message, "error"));
  useEffect(() => { load(); }, []);
  const save = async (key) => {
    try { await api(`/api/secrets/${key}`, { method: "PUT", body: { value: values[key] || "" } }); setValues({ ...values, [key]: "" }); toast(t("saved_restart")); load(); }
    catch (e) { toast(e.message, "error"); }
  };
  const remove = async (key) => { await api(`/api/secrets/${key}`, { method: "DELETE" }); load(); };
  return html`<div class="card form">
    ${items.map((s) => html`<div class="field"><span>${s.label || s.name}<div class="faint mono">${s.name}</div></span>
      <div class="row">
        <input class="input" type="password" autocomplete="off" placeholder=${s.set ? "••••••••" : t("not_set")}
          value=${values[s.name] || ""} onInput=${(e) => setValues({ ...values, [s.name]: e.target.value })} />
        <button class="btn" onClick=${() => save(s.name)}>${t("save")}</button>
        ${s.set ? html`<button class="btn ghost" onClick=${() => remove(s.name)}>${t("remove")}</button>` : null}
      </div></div>`)}
    <div class="row"><input class="input mono" placeholder="OTHER_API_KEY" value=${name} onInput=${(e) => setName(e.target.value.toUpperCase())} />
      <button class="btn" onClick=${() => { if (name) { setItems([...items, { name, label: "", set: false }]); setName(""); } }}>${t("add")}</button></div>
    <p class="muted">${t("secrets_help")}</p>
  </div>`;
}

export function ScheduleList({ toast }) {
  const [jobs, setJobs] = useState([]);
  const [cron, setCron] = useState("30 7 * * 1-5");
  const [text, setText] = useState("");
  const [speak, setSpeak] = useState(false);
  const load = () => api("/api/schedules").then(setJobs).catch((e) => toast(e.message, "error"));
  useEffect(() => { load(); }, []);
  const call = async (path, method, body) => {
    try { const r = await api(path, { method, body }); if (r?.message) toast(r.message); load(); } catch (e) { toast(e.message, "error"); }
  };
  const add = async () => { await call("/api/schedules", "POST", { cron, text, speak }); setText(""); };
  return html`<div class="card form">
    ${jobs.length ? html`<table class="table"><tr><th>${t("when")}</th><th>${t("sched_what")}</th><th>${t("next_run")}</th><th></th></tr>
      ${jobs.map((j) => html`<tr class=${j.enabled ? "" : "faint"}>
        <td class="mono">${j.cron}</td><td>${j.name || j.text || j.prompt || j.skill}${j.speak ? " 🔊" : ""}</td>
        <td>${j.next ? new Date(j.next).toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" }) : "–"}</td>
        <td class="row" style="justify-content:flex-end">
          <button class="btn ghost" onClick=${() => call(`/api/schedules/${j.id}/run`, "POST")}>${t("run_now")}</button>
          ${j.source === "store" ? html`
            <button class="btn ghost" onClick=${() => call(`/api/schedules/${j.id}`, "PATCH", { enabled: !j.enabled })}>${j.enabled ? t("pause") : t("resume")}</button>
            <button class="btn danger" onClick=${() => call(`/api/schedules/${j.id}`, "DELETE")}>${t("remove")}</button>` : html`<span class="faint">${t("from_config")}</span>`}
        </td></tr>`)}</table>` : html`<p class="muted">${t("no_schedules")}</p>`}
    <div class="row">
      <input class="input mono" style="width:150px" value=${cron} onInput=${(e) => setCron(e.target.value)} />
      <input class="input" style="flex:1" placeholder=${t("schedule_what")} value=${text} onInput=${(e) => setText(e.target.value)} />
      <label class="row"><input type="checkbox" checked=${speak} onChange=${(e) => setSpeak(e.target.checked)} /> 🔊</label>
      <button class="btn primary" onClick=${add}>${t("add")}</button>
    </div>
    <p class="muted">${t("cron_help")}</p>
  </div>`;
}

// Projects and agents: edited in the settings overlay, like the forms; those the
// forms added can be removed here (the config file's own stay).
export const PROJECT_FIELDS = (meta) => [
  ["path", "f_project_path", "text"], ["base_branch", "f_base_branch", "text"],
  ["test_command", "f_test_command", "text"], ["default_agent", "default_agent", "select", ["", ...meta.agents]],
  ["reviewer", "f_reviewer", "select", ["", ...meta.agents]], ["auto_review", "f_auto_review", "bool"],
  ["benchmark", "f_benchmark", "text"], ["forge", "f_forge", "select", ["", "auto", "github", "gitlab", "git"]],
  ["note", "f_note", "text"], ["toolchain", "f_toolchain", "select", ["", "auto", "godot", "none"]],
];

export const AGENT_FIELDS = (meta) => [
  ["type", "f_agent_type", "select", meta.agent_types || []], ["model", "f_model", "combo", meta.agent_models || []],
  ["role", "f_role", "text"], ["command", "f_command", "text"],
];

export function EntityEditor({ kind, fields, meta, onSaved, toast }) {
  const items = meta.values[kind] || {};
  const overlay = meta.overlay?.[kind] || {};
  const [name, setName] = useState("");
  const [first, setFirst] = useState("");
  const add = async (e) => {
    e.preventDefault();
    const key = name.trim();
    if (!/^[\w-]+$/.test(key) || !first.trim()) return toast(t("entity_invalid"), "error");
    try {
      await api("/api/settings", { method: "PUT", body: { changes: { [kind]: { [key]: { [fields[0][0]]: first.trim() } } } } });
      setName(""); setFirst(""); toast(t("saved")); onSaved();
    } catch (err) { toast(err.message, "error"); }
  };
  const remove = async (key) => {
    if (!(await confirmDialog(t("entity_remove_confirm", { name: key }), { danger: true }))) return;
    try { await api("/api/settings", { method: "PUT", body: { changes: { [kind]: { [key]: null } } } }); toast(t("saved")); onSaved(); }
    catch (err) { toast(err.message, "error"); }
  };
  return html`
    ${Object.keys(items).map((key) => html`<div class="card" style="margin:8px 0">
      <div class="row"><strong style="flex:1">${key}</strong>
        ${overlay[key] ? html`<button class="btn ghost" onClick=${() => remove(key)}>${t("remove")}</button>` : html`<span class="faint">${t("from_config")}</span>`}</div>
      <${Form} fields=${fields.map(([f, label, type, opts]) => [`${kind}.${key}.${f}`, label, type, opts])} meta=${meta} onSaved=${onSaved} toast=${toast} />
    </div>`)}
    <form class="row card" style="margin:8px 0" onSubmit=${add}>
      <input class="input" style="width:140px" placeholder=${t("entity_name")} value=${name} onInput=${(e) => setName(e.target.value)} />
      ${fields[0][2] === "select"
        ? html`<select class="select" value=${first} onChange=${(e) => setFirst(e.target.value)}><option value="">${t(fields[0][1])}</option>
            ${fields[0][3].map((o) => html`<option value=${o}>${o}</option>`)}</select>`
        : html`<input class="input" style="flex:1" placeholder=${t(fields[0][1])} value=${first} onInput=${(e) => setFirst(e.target.value)} />`}
      <button class="btn primary">${t("add")}</button></form>`;
}

export function BrainTest({ toast }) {
  const [text, setText] = useState("");
  const [out, setOut] = useState("");
  const [busy, setBusy] = useState(false);
  const run = async (args) => {
    setBusy(true); setOut("");
    try { setOut(await runTool("brains", args)); } catch (e) { toast(e.message, "error"); }
    setBusy(false);
  };
  return html`<div class="card form" style="margin-top:8px">
    <p class="muted">${t("brain_test_help")}</p>
    <form class="row" onSubmit=${(e) => { e.preventDefault(); if (text.trim()) run(["--test", text]); }}>
      <input class="input" style="flex:1" placeholder=${t("brain_test_placeholder")} value=${text} onInput=${(e) => setText(e.target.value)} />
      <button class="btn" disabled=${busy}>${t("brain_test")}</button>
      <button type="button" class="btn ghost" disabled=${busy} onClick=${() => run(["--replay", "50"])}>${t("brain_replay")}</button></form>
    ${busy ? html`<p class="muted">…</p>` : null}
    ${out ? html`<pre class="mono" style="white-space:pre-wrap;margin-top:8px">${out}</pre>` : null}
  </div>`;
}
