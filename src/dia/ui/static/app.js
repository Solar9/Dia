// Dia web UI: the app shell and the router. Views live in ./js/views, shared pieces in ./js.
// Plain ES modules with Preact + htm, so there is no build step.
import { render } from "preact";
import { useCallback, useEffect, useRef, useState } from "preact/hooks";
import { html } from "./js/html.js";
import { APP_HOME, IN_APP, TOKEN_KEY, api, onPhone, setOnPhone, setToken, token } from "./js/api.js";
import { lang, setLang, t } from "./js/i18n.js";
import { Icon } from "./js/ui/icons.js";
import { Login } from "./js/ui/login.js";
import { confirmDialog } from "./js/ui/dialog.js";
import { DiaLogo } from "./js/ui/logo.js";
import { Palette } from "./js/ui/palette.js";
import { VSplitter } from "./js/ui/splitter.js";
import { WindowControls, WindowEdges } from "./js/ui/window.js";
import { SIDEBAR_KEY, SPLIT_SIDEBAR, START_TASK, START_VIEW, THEME_KEY, VIEWS, applyTheme, hashParam, store, useSplitWidth } from "./js/util.js";
import { ChatView, TalkSheet } from "./js/views/chat.js";
import { CliView } from "./js/views/cli.js";
import { InboxView } from "./js/views/inbox.js";
import { MemoryView } from "./js/views/memory.js";
import { MissionsView } from "./js/views/missions.js";
import { SettingsView } from "./js/views/settings.js";
import { StatusView } from "./js/views/status.js";
import { TasksView } from "./js/views/tasks.js";
import { UsageView } from "./js/views/usage.js";

function App() {
  const [authed, setAuthed] = useState(Boolean(token));
  const [view, setView] = useState(START_VIEW || (START_TASK ? "tasks" : "inbox"));
  const [collapsed, setCollapsed] = useState(store(SIDEBAR_KEY) === "collapsed");
  const [sidebarW, setSidebarW, commitSidebarW] = useSplitWidth(SPLIT_SIDEBAR, 240, 180, 400);
  const [talking, setTalking] = useState(false);
  const [more, setMore] = useState(false);
  const [palette, setPalette] = useState(false);
  const [tasks, setTasks] = useState([]);
  const [status, setStatus] = useState(null);
  const [selected, setSelected] = useState(START_TASK);
  const [connected, setConnected] = useState(false);
  const [voice, setVoice] = useState("idle");
  const [looking, setLooking] = useState(false);
  const [toasts, setToasts] = useState([]);
  const [, rerender] = useState(0);
  const statusSoon = useRef(0);
  const toast = useCallback((text, kind = "info") => {
    const id = Math.random();
    setToasts((all) => [...all, { id, text, kind }]);
    setTimeout(() => setToasts((all) => all.filter((x) => x.id !== id)), kind === "error" ? 8000 : 4000);
  }, []);

  // "loading" until the first answer; "error" keeps the message, so a failed call is never silent.
  const [loaded, setLoaded] = useState({ tasks: "loading", status: "loading", error: "" });
  const failed = (which, e) => setLoaded((all) => ({ ...all, [which]: "error", error: e.message }));
  const loadTasks = useCallback(() => api("/api/tasks").then((list) => {
    setTasks(list);
    setLoaded((all) => ({ ...all, tasks: "ok", error: all.status === "error" ? all.error : "" }));
  }).catch((e) => {
    if (/token/.test(e.message)) { store(TOKEN_KEY, null); setToken(""); setAuthed(false); return; }
    failed("tasks", e);
  }), []);
  const loadStatus = useCallback(() => api("/api/status").then((s) => {
    if (s.language !== lang) { setLang(s.language); rerender((n) => n + 1); }
    // Dia keeps the theme: the app's, or on a paired phone the phone's (Settings → Look)
    setOnPhone(Boolean(s.device));
    if (s.theme && s.theme !== store(THEME_KEY)) applyTheme(s.theme);
    setStatus(s);
    setLoaded((all) => ({ ...all, status: "ok", error: all.tasks === "error" ? all.error : "" }));
  }).catch((e) => failed("status", e)), []);

  useEffect(() => { applyTheme(store(THEME_KEY) || "dark"); }, []);
  // The desktop window's tray menu (and links like #view=chat) switch the tab.
  useEffect(() => {
    window.diaNavigate = (name, task) => {
      setMore(false);
      if (task) { setSelected(task); setView("tasks"); } else if (VIEWS.includes(name)) setView(name);
    };
    const onHash = () => {
      setMore(false);
      const name = hashParam("view");
      if (VIEWS.includes(name)) setView(name);
      const task = hashParam("task");
      if (task) { setSelected(task); setView("tasks"); }
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  useEffect(() => { if (authed) { loadTasks(); loadStatus(); } }, [authed]);
  // Ctrl+B folds the sidebar down to its icons (and back); remembered on this device.
  const toggleSidebar = useCallback(() => setCollapsed((was) => {
    store(SIDEBAR_KEY, was ? "open" : "collapsed");
    return !was;
  }), []);
  useEffect(() => {
    const onKey = (e) => {
      if (!(e.ctrlKey || e.metaKey) || e.altKey || e.shiftKey) return;
      if (e.key.toLowerCase() === "b") { e.preventDefault(); toggleSidebar(); }
      if (e.key.toLowerCase() === "k") { e.preventDefault(); setPalette((was) => !was); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Live updates: task changes, CI/review news and the voice state.
  useEffect(() => {
    if (!authed) return;
    let ws, retry, closed = false;
    const connect = () => {
      const scheme = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${scheme}://${location.host}/ws?token=${encodeURIComponent(token)}`);
      ws.onopen = () => setConnected(true);
      ws.onclose = () => { setConnected(false); if (!closed) retry = setTimeout(connect, 2000); };
      ws.onmessage = (message) => {
        const data = JSON.parse(message.data);
        if (data.type === "task") {
          setTasks((all) => {
            const before = all.find((x) => x.id === data.task.id);
            const kept = before && before.commit_sha === data.task.commit_sha ? before.diffstat : undefined;
            return [{ diffstat: kept, ...data.task }, ...all.filter((x) => x.id !== data.task.id)]
              .sort((a, b) => b.created_at.localeCompare(a.created_at));
          });
          // a new commit waits for a decision: fetch its +/- once
          if (data.task.commit_sha && ["done", "failed", "published"].includes(data.task.status)) loadTasks();
          clearTimeout(statusSoon.current);
          statusSoon.current = setTimeout(loadStatus, 400);  // the counts changed
          window.dispatchEvent(new CustomEvent("dia-task", { detail: data.task }));
        } else if (data.type === "theme") {
          applyTheme((onPhone && data.phone) || data.name);
          window.dispatchEvent(new CustomEvent("dia-theme", { detail: data }));
        } else if (data.type === "event" && data.kind === "voice") {
          setVoice(data.message.split(":")[0]);
        } else if (data.type === "event" && data.kind === "camera") {
          if (data.message === "looking") toast(`📷 ${t("camera_on")}`);
          else loadStatus();
        } else if (data.type === "event" && data.kind === "quiet") {
          loadStatus();
        } else if (data.type === "event" && data.kind === "screen") {
          setLooking(data.message === "looking");
          if (data.message === "looking") toast(`👁 ${t("screen_looking")}`);
          else loadStatus();
        } else if (data.type === "event" && (data.kind === "stop" || data.kind === "resume")) {
          loadStatus();
          toast(data.kind === "stop" ? `🛑 ${t("stopped_all")}` : t("resumed"), data.kind === "stop" ? "error" : "info");
        } else if (data.type === "audit") {
          window.dispatchEvent(new CustomEvent("dia-audit", { detail: data.entry }));
        } else if (data.type === "event" && data.kind === "mission" && !/^(ready|failed|paused|done|integration)/.test(data.message)) {
          // step-by-step progress shows in Mission Control; only outcomes pop up
        } else if (data.type === "event") {
          toast(`${data.kind.toUpperCase()} · ${data.message}`);
        } else if (data.type === "error") {
          toast(data.message, "error");
        }
      };
    };
    connect();
    return () => { closed = true; clearTimeout(retry); ws && ws.close(); };
  }, [authed]);

  if (!authed) {
    return html`<${Login} onToken=${(value) => { setToken(store(TOKEN_KEY, value)); setAuthed(Boolean(value)); }} />`;
  }

  const toggleScreen = async () => {
    try { await api("/api/screen", { method: "POST", body: { on: !status.screen } }); loadStatus(); }
    catch (e) { toast(e.message, "error"); }
  };
  const toggleCamera = async () => {
    try { await api("/api/camera", { method: "POST", body: { on: !status.camera } }); loadStatus(); }
    catch (e) { toast(e.message, "error"); }
  };
  const toggleQuiet = async () => {
    try { await api("/api/quiet", { method: "POST", body: { on: !status.quiet } }); loadStatus(); }
    catch (e) { toast(e.message, "error"); }
  };
  const stopAll = async () => {
    if (!(await confirmDialog(t("stop_confirm"), { danger: true }))) return;
    try { await api("/api/stop", { method: "POST" }); loadStatus(); } catch (e) { toast(e.message, "error"); }
  };
  const resumeAll = async () => {
    try { await api("/api/resume", { method: "POST" }); loadStatus(); } catch (e) { toast(e.message, "error"); }
  };
  const toggleVoice = async () => {
    try { await api("/api/voice/toggle", { method: "POST" }); } catch (e) { toast(e.message, "error"); }
  };
  const [active, decisions] = [status?.counts?.running ?? 0, status?.counts?.waiting_for_you ?? 0];  // API: dia.core.taskstate
  const work = [["inbox", decisions || ""], ["tasks", active || ""], ["missions", ""], ["chat", ""], ["cli", ""]];
  const system = [["memory", ""], ["status", ""], ["usage", ""]];
  const open = (id) => { setSelected(id); setView("tasks"); setTalking(false); };
  const go = (key) => { setView(key); setMore(false); };
  // On the computer the microphone is Dia's own; a paired phone talks through its own.
  const talk = () => (status?.device ? setTalking(true) : toggleVoice());
  const navItem = ([key, count]) => html`
    <button class="nav-item ${view === key ? "active" : ""} ${key === "inbox" && count ? "has-badge" : ""}" title=${t(key)}
      aria-current=${view === key ? "page" : undefined} onClick=${() => go(key)}>
      <${Icon} name=${key} /><span class="nav-label">${t(key)}</span><span class="nav-count">${count}</span></button>`;
  const okAgents = status ? status.agents.filter((a) => a.ok).length : 0;

  return html`
    <div class="shell ${collapsed ? "collapsed" : ""}" style=${collapsed ? null : { "--sidebar-w": `${sidebarW}px` }}>
      <aside class="sidebar">
        <div class="brand" data-drag><${DiaLogo} /><span class="brand-name">dia</span>
          ${status?.version ? html`<button type="button" class="brand-version" title=${t("about_tab")}
            onClick=${(e) => { e.stopPropagation(); go("status"); setTimeout(() => document.getElementById("status-about")?.scrollIntoView({ behavior: "smooth" }), 50); }}>${status.version}</button>` : null}</div>
        <nav class="nav" aria-label="Dia">
          <div class="nav-group">${t("nav_work")}</div>
          ${work.map(navItem)}
          <div class="nav-group">${t("nav_system")}</div>
          <span class="nav-rule" aria-hidden="true"></span>
          ${system.map(navItem)}
          <span class="nav-fill"></span>
          ${navItem(["settings", ""])}
        </nav>
        <div class="sidebar-foot">
          ${status ? html`<button class="mic ${status.device ? "" : voice}" onClick=${talk} title=${status.device ? t("talk_to_dia") : `${t("talk_to_dia")} · dia voice toggle`} aria-label=${t("talk_to_dia")}>
            <span class="mic-orb"><${Icon} name="mic" size=${16} /></span>
            <span class="mic-text"><span class="mic-title">${t("talk_to_dia")}</span>
              <span class="mic-label">${status.device || voice === "idle" ? t("voice_ready") : t(`voice_${voice}`)}</span></span></button>` : null}
          ${status ? html`<div class="senses" role="group" aria-label=${t("senses")}>
            <button class="sense ${status.screen ? "on" : ""} ${looking ? "looking" : ""}" aria-pressed=${Boolean(status.screen)} aria-label=${status.screen ? t("screen_on") : t("screen_off")}
              title="${status.screen ? t("screen_on") : t("screen_off")} · ${t("screen_help")}" onClick=${toggleScreen}><${Icon} name="screen" size=${16} /></button>
            <button class="sense ${status.camera ? "on" : ""}" aria-pressed=${Boolean(status.camera)} aria-label=${status.camera ? t("camera_on") : t("camera_off")}
              title="${status.camera ? t("camera_on") : t("camera_off")} · ${t("camera_help")}" onClick=${toggleCamera}><${Icon} name="camera" size=${16} /></button>
            <button class="sense ${status.quiet || status.quiet_hours ? "on" : ""}" aria-pressed=${Boolean(status.quiet)} aria-label=${status.quiet ? t("quiet_on") : t("quiet_off")}
              title="${status.quiet ? t("quiet_on") : status.quiet_hours ? t("quiet_hours_on") : t("quiet_off")} · ${t("quiet_help")}" onClick=${toggleQuiet}>
              <${Icon} name=${status.quiet ? "muted" : status.quiet_hours ? "moon" : "speaker"} size=${16} /></button>
          </div>` : null}
          <div class="conn" title=${connected ? t("connected") : t("offline")}><span class="conn-dot ${connected ? "on" : ""}"></span>
            <span class="conn-text">${connected ? t("local_dia") : t("offline")}</span>
            ${status ? html`<span class="conn-agents">${t("agents_ready", { ok: okAgents, all: status.agents.length })}</span>` : null}
            ${IN_APP ? html` · <a href="#" onClick=${(e) => { e.preventDefault(); location.href = APP_HOME; }}>${t("change_server")}</a>` : null}</div>
        </div>
      </aside>
      ${collapsed ? null : html`<${VSplitter} width=${sidebarW} setWidth=${setSidebarW} commit=${commitSidebarW} min=${180} max=${400} def=${240} />`}
      <main class="main">
        <div class="topbar" data-drag>
          <button class="icon-btn sidebar-toggle" onClick=${toggleSidebar} aria-expanded=${!collapsed}
            title="${collapsed ? t("menu_expand") : t("menu_collapse")} (Ctrl+B)" aria-label=${collapsed ? t("menu_expand") : t("menu_collapse")}><${Icon} name="panel" /></button>
          <nav class="crumbs" aria-label=${t("breadcrumb")}><span class="hide-phone">${t("workspace")}</span><span class="sep hide-phone">/</span><h1>${t(view)}</h1></nav>
          <span class="spacer"></span>
          <button class="search-btn" onClick=${() => setPalette(true)} title=${t("search")} aria-label=${t("search")}>
            <${Icon} name="search" size=${16} /><span class="hide-phone">${t("search")}</span><kbd class="hide-phone">Ctrl K</kbd></button>
          ${active ? html`<span class="tag ok hide-phone">${t("running_count", { n: active })}</span>` : null}
          ${status && !status.halted ? html`<button class="btn danger-outline stop-btn" title=${t("stop_help")} onClick=${stopAll}><${Icon} name="stop" size=${11} /> ${t("stop")}</button>` : null}
          <${WindowControls} />
        </div>
        ${status?.halted ? html`<div class="halted-bar">🛑 ${t("halted")}
          <button class="btn primary" onClick=${resumeAll}>${t("resume_btn")}</button></div>` : null}
        <div class="content">
          ${loaded.error ? html`<div class="state error app-state" role="alert"><span>${t("load_failed")}: ${loaded.error}</span>
            <button class="btn ghost" onClick=${() => { setLoaded({ tasks: "loading", status: "loading", error: "" }); loadTasks(); loadStatus(); }}>${t("retry")}</button></div>` : null}
          ${view === "inbox" ? html`<${InboxView} loading=${loaded.tasks === "loading"} tasks=${tasks} status=${status} open=${open} go=${go} toast=${toast} reload=${loadTasks} />` : null}
          ${view === "tasks" ? html`<${TasksView} loading=${loaded.tasks === "loading"} tasks=${tasks} status=${status} selected=${selected} select=${setSelected} toast=${toast} reload=${loadTasks} />` : null}
          ${view === "chat" ? html`<${ChatView} open=${open} toast=${toast} />` : null}
          ${view === "cli" ? html`<${CliView} toast=${toast} status=${status} />` : null}
          ${view === "status" ? html`<${StatusView} status=${status} reload=${loadStatus} toast=${toast} />` : null}
          ${view === "usage" ? html`<${UsageView} toast=${toast} />` : null}
          ${view === "memory" ? html`<${MemoryView} toast=${toast} />` : null}
          ${view === "missions" ? html`<${MissionsView} status=${status} toast=${toast} open=${open} />` : null}
          ${view === "settings" ? html`<${SettingsView} toast=${toast} device=${status?.device} full=${status?.device_full} />` : null}
        </div>
      </main>
      <nav class="phone-bar" aria-label="Dia">
        ${[["inbox", decisions], ["tasks", active]].map(([key, count]) => html`<button class="phone-tab ${view === key && !more ? "active" : ""}"
          aria-current=${view === key && !more ? "page" : undefined} onClick=${() => go(key)}>
          <span class="phone-icon"><${Icon} name=${key} size=${22} />${count ? html`<span class="phone-badge">${count}</span>` : null}</span>${t(key)}</button>`)}
        <button class="phone-mic ${status?.device ? "" : voice}" onClick=${talk} aria-label=${t("talk_to_dia")}><${Icon} name="mic" size=${26} /></button>
        <button class="phone-tab ${view === "chat" && !more ? "active" : ""}" onClick=${() => go("chat")}>
          <span class="phone-icon"><${Icon} name="chat" size=${22} /></span>${t("chat")}</button>
        <button class="phone-tab ${more ? "active" : ""}" aria-expanded=${more} onClick=${() => setMore(!more)}>
          <span class="phone-icon"><${Icon} name="more" size=${22} /></span>${t("more")}</button>
      </nav>
      ${more ? html`<div class="sheet-backdrop" onClick=${() => setMore(false)}></div>
        <div class="sheet" role="dialog" aria-label=${t("more")}>
          ${[...work.slice(2).filter(([key]) => key !== "chat" && !(key === "cli" && status?.device)), ...system, ["settings", ""]].map(([key]) => html`
            <button class="sheet-item ${view === key ? "active" : ""}" onClick=${() => go(key)}><${Icon} name=${key} />${t(key)}</button>`)}
          ${status ? html`<div class="sheet-row">
            <button class="sense ${status.screen ? "on" : ""}" aria-pressed=${Boolean(status.screen)} title=${t("screen_help")} onClick=${toggleScreen}><${Icon} name="screen" size=${16} /> ${status.screen ? t("screen_on") : t("screen_off")}</button>
            <button class="sense ${status.camera ? "on" : ""}" aria-pressed=${Boolean(status.camera)} title=${t("camera_help")} onClick=${toggleCamera}><${Icon} name="camera" size=${16} /> ${status.camera ? t("camera_on") : t("camera_off")}</button>
            <button class="sense ${status.quiet ? "on" : ""}" aria-pressed=${Boolean(status.quiet)} title=${t("quiet_help")} onClick=${toggleQuiet}><${Icon} name=${status.quiet ? "muted" : "speaker"} size=${16} /> ${status.quiet ? t("quiet_on") : t("quiet_off")}</button>
          </div>` : null}
          <div class="conn"><span class="conn-dot ${connected ? "on" : ""}"></span><span class="conn-text">${connected ? t("connected") : t("offline")}</span>
            ${IN_APP ? html`<a href="#" onClick=${(e) => { e.preventDefault(); location.href = APP_HOME; }}>${t("change_server")}</a>` : null}</div>
        </div>` : null}
      ${palette ? html`<${Palette} tasks=${tasks} open=${open} onClose=${() => setPalette(false)} items=${[
        ...VIEWS.map((key) => ({ kind: "view", icon: key, label: t(key), run: () => go(key) })),
        { kind: "action", icon: "tasks", label: t("new_task"), run: () => go("inbox") },
        { kind: "action", icon: "mic", label: t("talk_to_dia"), run: talk },
        { kind: "action", icon: "panel", label: collapsed ? t("menu_expand") : t("menu_collapse"), hint: "Ctrl+B", run: toggleSidebar },
        ...(status ? [{ kind: "action", icon: status.quiet ? "speaker" : "muted", label: status.quiet ? t("quiet_off_action") : t("quiet_on_action"), run: toggleQuiet }] : []),
      ]} />` : null}
      ${talking ? html`<${TalkSheet} local=${status?.talk} quiet=${status?.quiet} open=${open} onClose=${() => setTalking(false)}
        onType=${() => { setTalking(false); go("chat"); }} />` : null}
      <div class="toasts" aria-live="polite" aria-atomic="false">${toasts.map((x) => html`<div key=${x.id} class="toast ${x.kind}" role=${x.kind === "error" ? "alert" : "status"}>${x.text}</div>`)}</div>
      <${WindowEdges} />
    </div>`;
}

render(html`<${App} />`, document.getElementById("app"));

// Installable app (PWA); service workers need https or localhost.
if ("serviceWorker" in navigator && window.isSecureContext) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
