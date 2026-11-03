import { useEffect, useState } from "preact/hooks";
import { html } from "../html.js";
import { api } from "../api.js";
import { t } from "../i18n.js";
import { VSplitter } from "../ui/splitter.js";
import { SPLIT_SETTINGS, applyTheme, useSplitWidth } from "../util.js";
import { PreferencesCard } from "./memory.js";
import { DesktopCard, Devices, Notifications } from "./settings_devices.js";
import { AGENT_FIELDS, BrainTest, EntityEditor, Form, LocalBrain, PROJECT_FIELDS, ScheduleList, Secrets, settingsForms } from "./settings_forms.js";
import { AboutCard } from "./status.js";

export const SETTINGS_TABS = [
  "assistant", "voice_brain", "look", "notifications",
  "agents_tab", "projects_tab", "memory_tab", "automation", "schedule",
  "integrations_tab", "devices_tab", "secrets",
  "desktop_tab", "security_tab", "config_file", "about_tab",
];

export const SETTINGS_NAV = [
  { group: "settings_you", items: ["assistant", "voice_brain", "look", "notifications"] },
  { group: "settings_work", items: ["agents_tab", "projects_tab", "memory_tab", "automation", "schedule"] },
  { group: "settings_connect", items: ["integrations_tab", "devices_tab", "secrets"] },
  { group: "settings_computer", items: ["desktop_tab", "security_tab", "config_file", "about_tab"] },
];

// One theme choice: the app's, or the phone's / the widget's, which can follow the app's.
export function ThemeChoice({ label, help, value, follows, themes, onPick, system = true }) {
  const own = follows === undefined || Boolean(value);
  const names = [...(system ? ["system"] : []), ...themes.built_in, ...themes.custom];
  const start = follows === "system" && !system ? "dark" : follows;  // the widget cannot follow it
  return html`<section class="theme-choice">
    <div class="label">${label}</div>
    <p class="muted">${help}</p>
    ${follows !== undefined ? html`<div class="segmented" role="radiogroup" aria-label=${label}>
      <button role="radio" aria-checked=${!own} class=${!own ? "on" : ""} onClick=${() => onPick(null)}>${t("theme_same", { name: follows })}</button>
      <button role="radio" aria-checked=${own} class=${own ? "on" : ""} onClick=${() => !own && onPick(start)}>${t("theme_own")}</button>
    </div>` : null}
    ${own ? html`<div class="theme-list">
      ${names.map((name) => html`<button class="theme-pick ${value === name ? "on" : ""}" aria-pressed=${value === name}
        onClick=${() => onPick(name)}><span class="theme-dot" data-theme=${name}></span>${name === "system" ? t("theme_system") : name}
        ${themes.custom.includes(name) ? html`<span class="faint">${t("custom_theme")}</span>` : null}</button>`)}
    </div>` : null}
  </section>`;
}

export function SettingsView({ toast, device: remote, full }) {
  // A paired phone sees its look and schedule; one with full access nearly everything.
  const device = remote && !full ? remote : null;
  const [tab, setTab] = useState(device ? "look" : "assistant");
  const [meta, setMeta] = useState(null);
  const [themes, setThemes] = useState(null);
  const [chosen, setChosen] = useState(null);  // {name, phone, widget}
  const [config, setConfig] = useState(null);
  const [navW, setNavW, commitNavW] = useSplitWidth(SPLIT_SETTINGS, 200, 160, 320);
  const loadMeta = () => api("/api/settings").then(setMeta).catch((e) => toast(e.message, "error"));
  useEffect(() => {
    api("/api/themes").then(setThemes).catch((e) => toast(e.message, "error"));
    api("/api/theme").then(setChosen).catch((e) => toast(e.message, "error"));
    if (!device) { loadMeta(); api("/api/config").then(setConfig).catch((e) => toast(e.message, "error")); }
  }, [device]);
  // which: "name" (the app), "phone" or "widget"; value: a theme, or null for the app's
  const pick = async (which, value) => {
    try {
      const answer = await api("/api/theme", { method: "PUT", body: { [which]: value } });
      setChosen(answer);
      applyTheme(answer.effective);
    } catch (e) { toast(e.message, "error"); }
  };
  useEffect(() => {  // switched elsewhere (another window, the phone)
    const onTheme = (e) => setChosen((was) => ({ ...was, ...e.detail }));
    window.addEventListener("dia-theme", onTheme);
    return () => window.removeEventListener("dia-theme", onTheme);
  }, []);
  const saveFile = async () => {
    try { await api("/api/config", { method: "PUT", body: { text: config.text } }); toast(t("saved_restart")); }
    catch (e) { toast(e.message, "error"); }
  };
  // Phone: look, notifications, schedule. Paired remote without full access: no secrets/devices/desktop.
  const hidden = device ? SETTINGS_TABS.filter((k) => !["look", "schedule", "notifications", "about_tab"].includes(k))
    : remote ? ["secrets", "devices_tab", "desktop_tab"] : [];
  const tabs = SETTINGS_TABS.filter((k) => !hidden.includes(k));
  const allowed = new Set(tabs);
  const nav = SETTINGS_NAV.map((g) => ({ ...g, items: g.items.filter((k) => allowed.has(k)) })).filter((g) => g.items.length);
  const forms = meta ? settingsForms(meta) : null;
  const form = (key) => (forms ? html`<${Form} fields=${forms[key]} meta=${meta} onSaved=${loadMeta} toast=${toast} />` : "…");
  const body = (() => {
    if (tab === "assistant") return html`${form("assistant")}
      <${PreferencesCard} toast=${toast} />`;
    if (tab === "voice_brain") return html`
      ${forms?.voice ? form("voice") : html`<p class="muted">${t("voice_off")}</p>`}
      <div class="label section">${t("brains")}</div>
      ${meta ? html`<${LocalBrain} meta=${meta} onSaved=${loadMeta} toast=${toast} />` : null}
      <${BrainTest} toast=${toast} />`;
    if (tab === "agents_tab") return html`${form("agents")}
      <div class="label section">${t("your_agents")}</div>
      ${meta ? html`<${EntityEditor} kind="agents" fields=${AGENT_FIELDS(meta)} meta=${meta} onSaved=${loadMeta} toast=${toast} />` : null}`;
    if (tab === "projects_tab") return html`<p class="muted">${t("projects_help")}</p>
      ${meta ? html`<${EntityEditor} kind="projects" fields=${PROJECT_FIELDS(meta)} meta=${meta} onSaved=${loadMeta} toast=${toast} />` : null}`;
    if (tab === "memory_tab") return html`${form("memory")}<p class="muted">${t("memory_help")}</p>`;
    if (tab === "automation") return form("automation");
    if (tab === "integrations_tab") return html`${form("integrations")}
      ${forms?.discord ? html`<div class="label section">Discord</div>${form("discord")}` : null}
      <p class="muted">${t("integrations_help")}</p>`;
    if (tab === "schedule") return html`<${ScheduleList} toast=${toast} />`;
    if (tab === "secrets") return html`<${Secrets} toast=${toast} />`;
    if (tab === "notifications") return html`
      <${Notifications} toast=${toast} />
      ${form("notify")}`;
    if (tab === "devices_tab") return html`
      <${Devices} toast=${toast} />
      <div class="label section">${t("remote_access")}</div>${form("remote")}`;
    if (tab === "look") return html`
      ${chosen && themes ? html`
        ${device ? null : html`<${ThemeChoice} label=${t("theme_app")} help=${t("theme_app_help")} value=${chosen.name}
          themes=${themes} onPick=${(name) => pick("name", name)} />`}
        <${ThemeChoice} label=${t("theme_phone")} help=${t("theme_phone_help")} value=${chosen.phone} follows=${chosen.name}
          themes=${themes} onPick=${(name) => pick("phone", name)} />
        ${device ? null : html`<${ThemeChoice} label=${t("theme_widget")} help=${t("theme_widget_help")} value=${chosen.widget}
          follows=${chosen.name} themes=${themes} system=${false} onPick=${(name) => pick("widget", name)} />`}` : "…"}
      <p class="muted">${t("themes_help")} <code>${themes?.dir || "~/.config/dia/themes"}</code></p>
      ${device ? html`<p class="muted section">${t("device_note", { name: device })}</p>` : null}`;
    if (tab === "desktop_tab") return html`
      <${DesktopCard} toast=${toast} />
      ${forms ? html`<div class="label section">${t("app_window")}</div>${form("app")}<p class="muted">${t("app_window_help")}</p>
        ${form("computer")}` : null}`;
    if (tab === "security_tab") return form("security");
    if (tab === "about_tab") return html`<${AboutCard} />`;
    if (tab === "config_file") return config ? html`
      <p class="faint mono">${config.path}</p>
      ${meta?.settings_path ? html`<p class="muted">${t("overlay_note")} <code>${meta.settings_path}</code></p>` : null}
      <textarea class="textarea config-editor" value=${config.text}
        onInput=${(e) => setConfig({ ...config, text: e.target.value })}></textarea>
      <div class="row" style="margin-top:8px"><button class="btn primary" onClick=${saveFile}>${t("save")}</button></div>` : "…";
    return null;
  })();
  return html`
    <div class="page wide settings">
      <div class="page-head">
        <h1>${t("settings")}</h1>
        <p class="muted">${t("settings_help")}</p>
      </div>
      <div class="settings-layout" style=${{ "--settings-nav-w": `${navW}px` }}>
        <nav class="settings-nav" aria-label=${t("settings")}>
          ${nav.map((g) => html`<div class="settings-group">
            <div class="nav-group">${t(g.group)}</div>
            ${g.items.map((k) => html`<button type="button" class="settings-nav-item ${tab === k ? "active" : ""}"
              onClick=${() => setTab(k)}>${t(k)}</button>`)}
          </div>`)}
        </nav>
        <${VSplitter} width=${navW} setWidth=${setNavW} commit=${commitNavW} min=${160} max=${320} def=${200} />
        <div class="settings-main">
          <div class="settings-panel-head">
            <h2>${t(tab)}</h2>
          </div>
          ${body}
        </div>
      </div>
    </div>`;
}
