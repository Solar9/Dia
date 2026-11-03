import { useEffect, useState } from "preact/hooks";
import { html } from "../html.js";
import { api } from "../api.js";
import { lang, t } from "../i18n.js";
import { ResourceState, useResource } from "../ui/resource.js";
import { confirmDialog, promptDialog } from "../ui/dialog.js";
import { ago } from "../util.js";

export function RuntimeCard({ state, act, busy }) {
  if (!state?.available) return null;
  const p = state.policy;
  const configure = (patch) => act("startup", { ...p, ...patch });
  const word = (table, key) => table?.[key]?.[lang] || table?.[key]?.en || key;
  const run = async (component, verb) => {
    const what = `${component === "dia" ? "Dia" : "Ollama"}: ${word(state.words?.verbs, verb)}`;
    if (verb !== "start" && !(await confirmDialog(`${what}\n${t("svc_confirm")}`, { danger: true, ok: word(state.words?.verbs, verb) }))) return;
    act("runtime", { component, verb, confirmed: true });
  };
  const op = state.operation;
  return html`<div class="label section">${t("svc_title")}</div>
    <div class="card form">
      ${op ? html`<p class=${op.state === "failed" ? "error" : "muted"} role="status">${t("svc_last")}: ${op.component === "dia" ? "Dia" : "Ollama"} · ${word(state.words?.verbs, op.verb)} · ${op.label?.[lang] || op.label?.en || op.state}${op.error ? `: ${op.error}` : ""}</p>` : null}
      <label class="row"><input type="checkbox" checked=${state.login_entry} disabled=${busy}
        onChange=${(e) => configure({ autostart: e.target.checked })} />
        ${t("svc_login")}</label>
      <label class="field"><span>Ollama</span><select class="input" value=${p.ollama} disabled=${busy}
        onChange=${(e) => configure({ ollama: e.target.value })}>
        <option value="with-dia">${t("svc_with_dia")}</option>
        <option value="independent">${t("svc_independent")}</option>
        <option value="manual">${t("svc_manual")}</option>
      </select></label>
      <label class="row"><input type="checkbox" checked=${p.warmup} disabled=${busy || state.warmup.load === "not-found"}
        onChange=${(e) => configure({ warmup: e.target.checked })} />
        ${t("svc_warm")}</label>
      <p class="muted">${t("svc_note")}</p>
      ${["dia", "ollama"].map((c) => html`<div class="row">
        <span style="flex:1">${c === "dia" ? "Dia" : "Ollama"}: ${state[c].label?.[lang] || state[c].label?.en || state[c].active} · ${state[c].enabled}</span>
        ${["start", "stop", "restart"].map((v) => html`<button class="btn ghost" disabled=${busy || !state[c].actions?.includes(v)}
          onClick=${() => run(c, v)}>${word(state.words?.verbs, v)}</button>`)}
        <button class="btn ghost" onClick=${() => act("logs", { component: c })}>${t("svc_logs")}</button>
      </div>`)}
    </div>`;
}

export function DesktopCard({ toast }) {
  const [state, setState] = useState(null);
  const [busy, setBusy] = useState(false);
  const [logs, setLogs] = useState("");
  const [lastOp, setLastOp] = useState(null);
  const [loadError, setLoadError] = useState("");
  const load = () => api("/api/desktop").then((next) => {
    setLoadError("");
    // A service action runs in the background: say how it ended once it does.
    const op = next?.runtime?.operation;
    const key = op ? `${op.component}${op.verb}${op.state}${op.at || ""}` : "";
    if (op && key !== lastOp && lastOp !== null && (op.state === "done" || op.state === "failed")) {
      const verb = next.runtime.words?.verbs?.[op.verb]?.[lang] || op.verb;
      toast(`${op.component === "dia" ? "Dia" : "Ollama"}: ${verb} · ${op.label?.[lang] || op.state}${op.error ? `: ${op.error}` : ""}`, op.state === "failed" ? "error" : "info");
    }
    setLastOp(key);
    setState(next);
  }).catch((e) => setLoadError(e.message));
  useEffect(() => { load(); const timer = setInterval(load, 5000); return () => clearInterval(timer); }, []);
  const act = async (action, body) => {
    setBusy(true);
    try { const r = await api(`/api/desktop/${action}`, { method: "POST", body: body || {} }); if (action === "logs") setLogs(r.message); else toast(r.message || r.error); }
    catch (e) { toast(e.message, "error"); }
    setBusy(false); load();
  };
  if (!state) return loadError ? html`<div class="state error" role="alert"><span>${t("load_failed")}: ${loadError}</span>
    <button class="btn ghost" onClick=${load}>${t("retry")}</button></div>` : null;
  const sc = state.shortcuts;
  return html`<${RuntimeCard} state=${state.runtime} act=${act} busy=${busy} />
    ${logs ? html`<pre class="card mono" style="white-space:pre-wrap">${logs}</pre>` : null}
    <div class="label section">${t("desktop_integration")}</div>
    <div class="card form" style="margin-top:8px">
      <div class="row"><span style="flex:1">${t("shortcuts")}: ${sc.menu ? t("in_menu") : t("not_in_menu")}${sc.desktop ? ` · ${t("on_desktop")}` : ""}${sc.autostart ? ` · ${t("at_login")}` : ""}</span>
        <button class="btn" disabled=${busy} onClick=${() => act("shortcuts", { desktop: true, autostart: sc.autostart })}>${sc.menu ? t("refresh_shortcuts") : t("add_shortcuts")}</button>
        
        ${sc.menu ? html`<button class="btn ghost" disabled=${busy} onClick=${() => act("remove-shortcuts")}>${t("remove")}</button>` : null}</div>
      ${state.widget !== null ? html`<div class="row" style="margin-top:8px"><span style="flex:1">${t("kde_widget")}: ${state.widget ? t("installed") : t("not_installed")}</span>
        <button class="btn" disabled=${busy} onClick=${() => act("widget")}>${state.widget ? t("update") : t("install")}</button></div>` : null}
      <p class="muted">${t("desktop_help")}</p>
    </div>`;
}

export function urlKey(base64) {
  const padded = (base64 + "=".repeat((4 - (base64.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/");
  return Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
}

export function Notifications({ toast }) {
  const [info, setInfo] = useState(null);
  const [on, setOn] = useState(false);
  const supported = "serviceWorker" in navigator && "PushManager" in window && window.isSecureContext;
  const pushRes = useResource("/api/push", { on: setInfo });
  useEffect(() => {
    if (supported) navigator.serviceWorker.ready.then((r) => r.pushManager.getSubscription()).then((s) => setOn(Boolean(s)));
  }, []);
  const enable = async () => {
    try {
      if (await Notification.requestPermission() !== "granted") throw new Error(t("push_denied"));
      const registration = await navigator.serviceWorker.ready;
      const sub = await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlKey(info.key) });
      await api("/api/push/subscribe", { method: "POST", body: sub.toJSON() });
      setOn(true);
      toast(t("push_on"));
    } catch (e) { toast(e.message, "error"); }
  };
  const disable = async () => {
    const registration = await navigator.serviceWorker.ready;
    const sub = await registration.pushManager.getSubscription();
    if (sub) { await api("/api/push/unsubscribe", { method: "POST", body: { endpoint: sub.endpoint } }); await sub.unsubscribe(); }
    setOn(false);
  };
  const test = async () => { try { toast((await api("/api/push/test", { method: "POST" })).message); } catch (e) { toast(e.message, "error"); } };
  if (!info) return html`<${ResourceState} res=${pushRes} quiet />`;
  return html`
    <div class="label section">${t("notifications")}</div>
    ${!info.available ? html`<p class="muted">${t("push_missing")}</p>`
      : !supported ? html`<p class="muted">${t("push_https")}</p>`
      : html`<div class="row" style="margin-top:8px">
          ${on ? html`<button class="btn" onClick=${disable}>${t("push_disable")}</button>
                   <button class="btn ghost" onClick=${test}>${t("push_test")}</button>`
               : html`<button class="btn primary" onClick=${enable}>${t("push_enable")}</button>`}
        </div>`}`;
}

export function Devices({ toast }) {
  const res = useResource("/api/devices");
  const info = res.data;
  const [name, setName] = useState("");
  const [paired, setPaired] = useState(null);
  const load = res.reload;
  const pair = async () => {
    try { setPaired(await api("/api/devices", { method: "POST", body: { name: name.trim() || "phone" } })); setName(""); load(); }
    catch (e) { toast(e.message, "error"); }
  };
  const revoke = async (id) => {
    try { await api(`/api/devices/${id}`, { method: "DELETE" }); load(); } catch (e) { toast(e.message, "error"); }
  };
  const setFull = async (id, full) => {
    if (full && !(await confirmDialog(t("full_access_confirm"), { danger: true }))) return;
    try { await api(`/api/devices/${id}`, { method: "PATCH", body: { full } }); load(); } catch (e) { toast(e.message, "error"); }
  };
  if (!info) return html`<${ResourceState} res=${res} quiet />`;
  return html`
    <div class="label section">${t("devices")}</div>
    ${!info.remote ? html`<p class="muted">${t("remote_off")}</p>` : null}
    ${info.devices.map((d) => html`<div class="row card" style="margin:8px 0">
      <strong style="flex:1">${d.name}</strong>
      <span class="faint">${d.last_seen ? ago(d.last_seen) : t("never")}</span>
      <label class="row muted" title=${t("full_access_help")}><input type="checkbox" checked=${d.full} onChange=${(e) => setFull(d.id, e.target.checked)} /> ${t("full_access")}</label>
      <button class="btn danger" onClick=${() => revoke(d.id)}>${t("revoke")}</button></div>`)}
    <div class="row" style="margin-top:8px">
      <input class="input" placeholder=${t("device_name")} value=${name} onInput=${(e) => setName(e.target.value)} />
      <button class="btn primary" onClick=${pair}>${t("pair")}</button>
    </div>
    ${paired ? html`<div class="card pairing section">
      ${paired.qr_svg ? html`<div class="qr" dangerouslySetInnerHTML=${{ __html: paired.qr_svg }}></div>` : null}
      <div style="min-width:0">
        <p>${t(paired.url ? "pair_scan" : "pair_no_url")}</p>
        ${paired.url ? html`<p class="mono break">${paired.url}</p>` : html`<p class="mono break">${paired.token}</p>`}
        <p class="faint">${t("pair_once")}</p>
        <button class="btn" onClick=${() => setPaired(null)}>${t("hide")}</button>
      </div></div>` : null}`;
}
