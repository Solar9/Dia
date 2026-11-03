import { useEffect, useRef, useState } from "preact/hooks";
import { html } from "../html.js";
import { api } from "../api.js";
import { t } from "../i18n.js";
import { ResourceState, useResource } from "../ui/resource.js";
import { VSplitter } from "../ui/splitter.js";
import { confirmDialog, promptDialog } from "../ui/dialog.js";
import { SPLIT_CLI, useSplitWidth } from "../util.js";
import { MessageList } from "./chat.js";

export const RESUMABLE = ["claude-code", "codex", "cursor"];

// A new agent session started here: the agent, its model and the project's folder.
// Submit hands the request to the parent immediately so the form is not stuck on
// "Starting…" for the whole first answer (which can take minutes).
export function NewCliSession({ status, onSubmit, onCancel }) {
  const agents = (status?.agents || []).filter((a) => RESUMABLE.includes(a.type));
  const [agent, setAgent] = useState(agents[0]?.name || "");
  const [model, setModel] = useState("");
  const [project, setProject] = useState(status?.projects?.[0]?.name || "");
  const [mode, setMode] = useState("edit");
  const [web, setWeb] = useState(false);
  const [text, setText] = useState("");
  const info = agents.find((a) => a.name === agent);
  const start = (e) => {
    e.preventDefault();
    if (!text.trim() || !project) return;
    onSubmit({ agent, model, project, mode, web, text: text.trim() });
  };
  if (!agents.length) return html`<div class="empty">${t("cli_new_none")}</div>`;
  return html`<form class="page cli-new" onSubmit=${start}>
    <h2>${t("cli_new")}</h2>
    <p class="muted">${t("cli_new_help")}</p>
    <label class="field"><span>${t("agent")}</span>
      <select class="select" value=${agent} onChange=${(e) => { setAgent(e.target.value); setModel(""); }}>
        ${agents.map((a) => html`<option value=${a.name} disabled=${!a.ok}>${a.name} · ${a.type}${a.ok ? "" : ` (${t("agent_unavailable")})`}</option>`)}
      </select></label>
    <label class="field"><span>${t("model")}</span>
      <input class="input" list="cli-models" value=${model} placeholder=${`${info?.model || t("auto")}`} onInput=${(e) => setModel(e.target.value)} />
      <datalist id="cli-models">${(info?.models || []).map((m) => html`<option value=${m}></option>`)}</datalist></label>
    <label class="field"><span>${t("project")}</span>
      <select class="select" value=${project} onChange=${(e) => setProject(e.target.value)}>
        ${(status?.projects || []).map((p) => html`<option value=${p.name}>${p.name} · ${p.path}</option>`)}
      </select></label>
    <label class="field"><span>${t("mode")}</span>
      <select class="select" value=${mode} onChange=${(e) => setMode(e.target.value)}>
        <option value="edit">${t("edit")}</option>
        <option value="read-only">${t("read_only")}</option>
      </select></label>
    <label class="field"><span>${t("cli_web")}</span>
      <input type="checkbox" checked=${web} onChange=${(e) => setWeb(e.target.checked)} /></label>
    <textarea class="textarea" placeholder=${t("cli_new_first")} value=${text} onInput=${(e) => setText(e.target.value)}
      onKeyDown=${(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) start(e); }}></textarea>
    <div class="row">
      <button class="btn primary" disabled=${!text.trim() || !project}>${t("cli_new_start")}</button>
      <button type="button" class="btn ghost" onClick=${onCancel}>${t("cancel")}</button>
    </div>
  </form>`;
}

export function CliView({ toast, status }) {
  const [creating, setCreating] = useState(false);
  const [pending, setPending] = useState(null);  // {agent, project, text} while the first answer runs
  const [live, setLive] = useState([]);
  const [held, setHeld] = useState([]);
  const [key, setKey] = useState(null);
  const [talk, setTalk] = useState({ messages: [], available: true });
  const [notes, setNotes] = useState([]);  // local /help /status replies
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [cmds, setCmds] = useState({});
  const [slash, setSlash] = useState(-1);  // highlighted index in the / menu, -1 = closed
  const [listW, setListW, commitListW] = useSplitWidth(SPLIT_CLI, 280, 200, 480);
  const end = useRef(null);
  const heldRes = useResource("/api/cli-captured", { interval: 5000, on: setHeld });
  const liveRes = useResource("/api/cli-sessions", { interval: 5000, on: setLive });
  useResource("/api/cli-commands", { on: setCmds });
  const loadHeld = heldRes.reload;
  const startSession = async (payload) => {
    setCreating(false);
    setPending(payload);
    setNotes([]);
    setTalk({ messages: [{ role: "user", text: payload.text, at: Date.now() / 1000 }], available: true });
    try {
      const item = await api("/api/cli-captured", { method: "POST", body: payload });
      setPending(null);
      await loadHeld();
      setKey(`c:${item.id}`);
      toast(t("cli_new_started"));
    } catch (err) {
      setPending(null);
      toast(`${t("cli_new_failed")}: ${err.message}`, "error");
    }
  };
  const rows = [
    ...(pending ? [{ key: "pending", kind: pending.agent, cwd: pending.project, pending: true, captured: true }] : []),
    ...[
      ...held.map((c) => ({ ...c, key: `c:${c.id}`, captured: true, when: Date.parse(c.taken_at) || 0 })),
      ...live.map((s) => ({ ...s, key: `p:${s.pid}`, when: Date.now() - s.age_s * 1000 })),
    ].sort((a, b) => b.when - a.when),  // newest first, taken-over and running together
  ];
  const chosen = pending && (!key || key === "pending") ? rows[0]
    : rows.find((r) => r.key === key) || rows.find((r) => !r.pending) || rows[0];
  const path = chosen && !chosen.pending
    ? (chosen.captured ? `/api/cli-captured/${chosen.id}/transcript` : `/api/cli-sessions/${chosen.pid}/transcript`)
    : null;
  const talkRes = useResource(path, { interval: 4000, on: setTalk });
  const refresh = talkRes.reload;
  useEffect(() => { setNotes([]); setSlash(-1); }, [path]);
  useEffect(() => end.current?.scrollIntoView({ block: "end" }), [talk.messages.length, notes.length, chosen?.key, pending]);
  const age = (s) => (s < 90 ? `${Math.round(s)} s` : s < 5400 ? `${Math.round(s / 60)} min` : `${(s / 3600).toFixed(1)} h`);
  const folder = (s) => (s.cwd || "").split("/").filter(Boolean).slice(-2).join("/") || s.cwd || "";
  const catalog = cmds[chosen?.kind] || [];
  const typed = text.startsWith("/") ? text.slice(1).toLowerCase() : "";
  const matches = text.startsWith("/")
    ? catalog.filter((c) => c.cmd.slice(1).startsWith(typed) || c.cmd.includes(typed.split(/\s/)[0]))
    : [];
  const capture = async () => {
    if (!(await confirmDialog(t("cli_capture_confirm")))) return;
    try {
      const item = await api(`/api/cli-sessions/${chosen.pid}/capture`, { method: "POST" });
      setKey(`c:${item.id}`); await loadHeld(); toast(t("cli_captured"));
    } catch (e) { toast(e.message, "error"); }
  };
  const release = async () => {
    try {
      const r = await api(`/api/cli-captured/${chosen.id}`, { method: "DELETE" });
      setKey(null); await loadHeld(); toast(`${t("cli_released")}: ${r.resume}`);
    } catch (e) { toast(e.message, "error"); }
  };
  const note = (body) => setNotes((all) => [...all, { role: "system", text: body, at: Date.now() / 1000 }]);
  const patchSession = async (fields) => {
    const item = await api(`/api/cli-captured/${chosen.id}`, { method: "PATCH", body: fields });
    await loadHeld();
    return item;
  };
  const sendPrompt = async (message) => {
    setBusy(true);
    try {
      const r = await api(`/api/cli-captured/${chosen.id}/send`, { method: "POST", body: { text: message } });
      setText(""); setSlash(-1);
      if (r.id !== chosen.id) { await loadHeld(); setKey(`c:${r.id}`); } else await refresh();
    } catch (err) { toast(err.message, "error"); }
    setBusy(false);
  };
  const modeOf = (cmd, arg) => {
    const a = (arg || "").trim().toLowerCase();
    if (cmd === "plan") return a && a !== "on" ? null : "read-only";
    if (cmd === "mode") {
      if (["ask", "plan", "read-only", "readonly"].includes(a)) return "read-only";
      if (["edit", "agent"].includes(a)) return "edit";
      return null;
    }
    if (cmd === "permissions") {
      if (a === "plan") return "read-only";
      if (["default", "acceptedits", "bypasspermissions"].includes(a.replace(/\s/g, ""))) return "edit";
      return null;
    }
    if (cmd === "approvals") {
      if (["untrusted", "on-request", "on_request"].includes(a)) return "read-only";
      if (["never", "on-failure", "on_failure"].includes(a)) return "edit";
      return null;
    }
    return null;
  };
  const runLocal = async (cmd, arg) => {
    if (cmd === "help" || cmd === "commands") {
      const lines = catalog.map((c) => `${c.cmd}${c.args ? ` ${c.args}` : ""}  —  ${c.help}`).join("\n");
      note(`${t("cli_commands_help")}\n\n${lines}`);
      return true;
    }
    if (cmd === "status" || cmd === "about") {
      note(t("cli_status_text", {
        kind: chosen.kind, cwd: chosen.cwd || "—", model: chosen.model || t("auto"),
        mode: chosen.mode || "edit", web: chosen.web ? "on" : "off", resume: chosen.resume || "—",
      }));
      return true;
    }
    if (cmd === "release") { await release(); return true; }
    if (cmd === "model") {
      if (!arg) { note(`${t("model")}: ${chosen.model || t("auto")}`); return true; }
      await patchSession({ model: arg });
      toast(t("cli_model_set", { name: arg }));
      return true;
    }
    if (["plan", "mode", "permissions", "approvals"].includes(cmd)) {
      if (!arg && cmd !== "plan") {
        note(`${t("mode")}: ${chosen.mode || "edit"}`);
        return true;
      }
      const next = modeOf(cmd, arg);
      if (!next) return false;
      await patchSession({ mode: next });
      toast(t("cli_mode_set", { mode: next }));
      return true;
    }
    return false;
  };
  const send = async (e) => {
    e.preventDefault();
    const message = text.trim();
    if (!message || busy || chosen?.pending) return;
    if (message.startsWith("/")) {
      const [raw, ...rest] = message.slice(1).split(/\s+/);
      const cmd = (raw || "").toLowerCase();
      const arg = rest.join(" ");
      const known = catalog.some((c) => c.cmd.slice(1) === cmd);
      if (!known) { note(t("cli_unknown")); setText(""); setSlash(-1); return; }
      setText(""); setSlash(-1);
      if (await runLocal(cmd, arg)) return;
    }
    await sendPrompt(message);
  };
  const pickCmd = (c) => {
    setText(c.args ? `${c.cmd} ` : c.cmd);
    setSlash(-1);
  };
  const onInputKey = (e) => {
    if (slash >= 0 && matches.length) {
      if (e.key === "ArrowDown") { e.preventDefault(); setSlash((slash + 1) % matches.length); return; }
      if (e.key === "ArrowUp") { e.preventDefault(); setSlash((slash - 1 + matches.length) % matches.length); return; }
      if (e.key === "Tab") {
        e.preventDefault(); pickCmd(matches[Math.max(0, slash)]); return;
      }
      if (e.key === "Enter" && !e.shiftKey) {
        const head = text.trim().split(/\s+/)[0];
        if (catalog.some((c) => c.cmd === head)) return;
        e.preventDefault(); pickCmd(matches[Math.max(0, slash)]); return;
      }
      if (e.key === "Escape") { e.preventDefault(); setSlash(-1); return; }
    }
  };
  const shown = [...talk.messages, ...notes];
  return html`<div class="chat-split" style=${{ "--chat-list-w": `${listW}px` }}>
    <div class="chat-sessions">
      <button class="btn new-task" disabled=${Boolean(pending)} onClick=${() => setCreating(true)}>+ ${t("cli_new")}</button>
      <p class="muted" style="padding:8px">${t("cli_sessions_help")}</p>
      <${ResourceState} res=${liveRes} quiet />
      ${rows.length ? rows.map((r) => html`<button type="button" key=${r.key} class="session-row ${!creating && chosen?.key === r.key ? "active" : ""}" aria-current=${!creating && chosen?.key === r.key ? "true" : undefined} style="flex-direction:column;align-items:flex-start" onClick=${() => { if (!r.pending) { setKey(r.key); setCreating(false); } }}>
        <span class="session-title" style="max-width:100%"><strong>${r.kind}</strong> · ${folder(r)}</span>
        <span class="faint">${r.pending ? t("cli_new_starting")
          : r.captured ? `${r.started_in_app ? t("cli_new_here") : t("cli_in_app")}${r.model ? ` · ${r.model}` : ""}`
          : `${r.from_dia ? t("cli_from_dia") : t("cli_external")} · ${r.model || t("auto")} · ${age(r.age_s)}`}</span></button>`)
        : html`<p class="faint" style="padding:8px">${t("cli_none")}</p>`}
    </div>
    <${VSplitter} width=${listW} setWidth=${setListW} commit=${commitListW} min=${200} max=${480} def=${280} />
    ${creating ? html`<${NewCliSession} status=${status} onCancel=${() => setCreating(false)} onSubmit=${startSession} />` : html`
    <div class="chat">
      <div class="chat-head"><strong style="flex:1">${chosen ? `${chosen.kind} · ${chosen.cwd || ""}` : ""}</strong>
        ${chosen?.captured && !chosen.pending ? html`<select class="chip-select" title=${t("mode")} value=${chosen.mode || "edit"}
          onChange=${(e) => patchSession({ mode: e.target.value })}>
          <option value="edit">${t("edit")}</option>
          <option value="read-only">${t("read_only")}</option></select>
          <label class="chip-check" title=${t("cli_web")}><input type="checkbox" checked=${Boolean(chosen.web)}
            onChange=${(e) => patchSession({ web: e.target.checked })} /> ${t("cli_web")}</label>` : null}
        ${chosen && !chosen.captured && !chosen.pending ? html`<button class="btn" title=${t("cli_capture_help")} onClick=${capture}>${t("cli_capture")}</button>` : null}
        ${chosen?.captured && !chosen.pending ? html`<button class="btn ghost" title=${chosen.resume} onClick=${release}>${t("cli_release")}</button>` : null}</div>
      <div class="messages">
        ${chosen?.pending ? html`<div class="empty">${t("cli_new_working")}</div>` : null}
        ${path ? html`<${ResourceState} res=${talkRes} quiet />` : null}
        ${chosen && !chosen.pending && !talk.available ? html`<div class="empty">${t("cli_no_transcript")}</div>` : null}
        ${chosen && !chosen.pending && talk.available && !shown.length ? html`<div class="empty">${t("cli_empty")}</div>` : null}
        <${MessageList} messages=${shown} />
        ${busy || chosen?.pending ? html`<div class="msg dia">…</div>` : null}
        <div ref=${end}></div>
      </div>
      ${chosen?.captured && !chosen.pending ? html`<div class="cli-cmds" title=${t("cli_commands_help")}>
        ${catalog.map((c) => html`<button type="button" class="cli-cmd" title=${c.help} onClick=${() => pickCmd(c)}>${c.cmd}</button>`)}
      </div>
      <form class="chat-input" onSubmit=${send}>
        ${matches.length ? html`<div class="slash-menu" role="listbox">
          ${matches.map((c, i) => html`<button type="button" role="option" class=${`slash-item ${i === Math.max(0, slash) ? "active" : ""}`}
            onMouseEnter=${() => setSlash(i)} onClick=${() => pickCmd(c)}>
            <span class="mono">${c.cmd}${c.args ? ` ${c.args}` : ""}</span><span class="faint">${c.help}</span></button>`)}
        </div>` : null}
        <input class="input" placeholder=${t("cli_cmd_hint")} value=${text} disabled=${busy}
          onInput=${(e) => { setText(e.target.value); setSlash(e.target.value.startsWith("/") ? 0 : -1); }}
          onKeyDown=${onInputKey} />
        <button class="btn primary" disabled=${busy || !text.trim()}>${t("send")}</button></form>`
        : chosen && !chosen.pending ? html`<div class="chat-input"><span class="faint">${t("cli_capture_help")}</span></div>` : null}
    </div>`}</div>`;
}
