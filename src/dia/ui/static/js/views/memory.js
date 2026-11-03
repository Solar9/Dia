import { useEffect, useState } from "preact/hooks";
import { html } from "../html.js";
import { api } from "../api.js";
import { t } from "../i18n.js";
import { Pill } from "../ui/icons.js";
import { Resource, ResourceState, useResource } from "../ui/resource.js";
import { VSplitter } from "../ui/splitter.js";
import { SPLIT_MEMORY, ago, useSplitWidth } from "../util.js";

export function PreferencesCard({ toast }) {
  const res = useResource("/api/preferences");
  const [text, setText] = useState("");
  const load = res.reload;
  const call = async (path, body) => {
    try { await api(path, { method: "POST", body }); load(); } catch (e) { toast(e.message, "error"); }
  };
  const add = async (e) => {
    e.preventDefault();
    if (!text.trim()) return;
    await call("/api/preferences", { text });
    setText("");
  };
  return html`<${Resource} res=${res} empty=${() => false}>${(prefs) => html`<div class="label">${t("preferences")}</div>
    <p class="faint">${t("preferences_help")}</p>
    ${prefs.configured.map((p) => html`<div class="card row" style="margin-bottom:8px"><span style="flex:1">${p}</span><span class="faint">${t("from_config")}</span></div>`)}
    ${prefs.accepted.map((p, i) => html`<div class="card row" style="margin-bottom:8px"><span style="flex:1">${p.text}</span>
      <button class="btn ghost" onClick=${() => call(`/api/preferences/${i}/remove`)}>${t("remove")}</button></div>`)}
    ${prefs.proposed.length ? html`<div class="label">${t("pref_proposed")}</div>` : null}
    ${prefs.proposed.map((p, i) => html`<div class="card fact"><div>${p.text}</div>
      <div class="row"><button class="btn primary" onClick=${() => call(`/api/preferences/${i}/accept`)}>${t("keep")}</button>
        <button class="btn ghost" onClick=${() => call(`/api/preferences/${i}/reject`)}>${t("forget")}</button></div></div>`)}
    <form class="row" onSubmit=${add}><input class="input" style="flex:1" placeholder=${t("pref_add")} value=${text} onInput=${(e) => setText(e.target.value)} />
      <button class="btn" aria-label=${t("add")}>+</button></form>`}<//>`;
}

export function DecisionsCard({ toast }) {
  const [rows, setRows] = useState([]);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState(null);
  const res = useResource("/api/decisions?limit=8", { on: setRows });
  const ask = async (e) => {
    e.preventDefault();
    if (!question.trim()) return setAnswer(null);
    try { setAnswer((await api(`/api/why?q=${encodeURIComponent(question)}`)).text); } catch (err) { toast(err.message, "error"); }
  };
  return html`<div class="label">${t("decisions")}</div>
    <form class="row" onSubmit=${ask}><input class="input" style="flex:1" placeholder=${t("why_placeholder")} value=${question} onInput=${(e) => setQuestion(e.target.value)} />
      <button class="btn">${t("why_ask")}</button></form>
    ${answer ? html`<pre class="prose" style="white-space:pre-wrap;margin-top:8px">${answer}</pre>` : null}
    <${ResourceState} res=${res} quiet />
    ${rows.map((d) => html`<div class="card" style="margin-top:8px"><div class="row"><span class="mono faint">${d.at.slice(0, 10)}</span>
      <${Pill} status=${["merged", "approved"].includes(d.outcome) ? "done" : ["discarded", "rejected", "rolled back", "changes_requested"].includes(d.outcome) ? "failed" : "planned"} label=${d.outcome} />
      <span style="flex:1">${d.title}</span></div>
      ${d.reason && d.kind !== "review" ? html`<div class="faint">${d.reason}</div>` : null}</div>`)}`;
}

export function ProfileCard({ toast }) {
  const res = useResource("/api/profile", { on: (d) => setText(d.text) });
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const load = res.reload;
  const call = async (path, options) => {
    setBusy(true);
    try { await api(path, options); load(); } catch (e) { toast(e.message, "error"); }
    setBusy(false);
  };
  return html`<${Resource} res=${res} empty=${() => false}>${(data) => html`<div class="label">${t("profile")}</div>
    <p class="faint">${t("profile_help")}</p>
    <textarea class="textarea mono" style="min-height:120px" placeholder=${t("profile_empty")} value=${text} onInput=${(e) => setText(e.target.value)}></textarea>
    <div class="row" style="margin-top:8px">
      <button class="btn primary" disabled=${busy || text === data.text} onClick=${() => call("/api/profile", { method: "PUT", body: { text } })}>${t("save")}</button>
      <button class="btn" disabled=${busy} onClick=${() => call("/api/profile/update", { method: "POST" })}>${t("profile_update")}</button></div>
    ${data.proposal ? html`<div class="label" style="margin-top:12px">${t("profile_proposed")}</div>
      <pre class="prose" style="white-space:pre-wrap">${data.proposal}</pre>
      <button class="btn primary" disabled=${busy} onClick=${() => call("/api/profile/accept", { method: "POST" })}>${t("profile_accept")}</button>` : null}`}<//>`;
}

export function MemoryView({ toast }) {
  const res = useResource("/api/memory");
  const info = res.data;
  const [note, setNote] = useState(null);
  const [text, setText] = useState("");
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState(null);
  const [listW, setListW, commitListW] = useSplitWidth(SPLIT_MEMORY, 360, 260, 560);
  const load = res.reload;
  const openNote = async (path) => {
    try { const n = await api(`/api/memory/note?path=${encodeURIComponent(path)}`); setNote(n); setText(n.text); }
    catch (e) { toast(e.message, "error"); }
  };
  const save = async () => {
    try { await api("/api/memory/note", { method: "PUT", body: { path: note.path, text } }); toast(t("saved")); load(); setNote({ ...note, text }); }
    catch (e) { toast(e.message, "error"); }
  };
  const search = async (e) => {
    e.preventDefault();
    if (!query.trim()) return setHits(null);
    try { setHits(await api(`/api/memory/search?q=${encodeURIComponent(query)}`)); } catch (err) { toast(err.message, "error"); }
  };
  const decide = async (taskId, accept, reject) => {
    try { await api(`/api/tasks/${taskId}/learn`, { method: "POST", body: { accept, reject } }); load(); }
    catch (e) { toast(e.message, "error"); }
  };
  if (!info) return html`<${ResourceState} res=${res} />`;
  if (!info.enabled) return html`<div class="page"><${PreferencesCard} toast=${toast} />
    <div class="section"><${ProfileCard} toast=${toast} /></div><div class="section"><${DecisionsCard} toast=${toast} /></div>
    <p class="muted">${t("memory_off_help")}</p></div>`;
  const groups = ["profile", "project", "howto", "journal", "other"].map((k) => [k, info.notes.filter((n) => n.kind === k)]).filter(([, n]) => n.length);
  const prefix = info.folder ? `${info.folder}/` : "";
  return html`
    <div class="split ${note ? "has-selected" : ""}" style=${{ "--list-w": `${listW}px` }}>
      <div class="list">
        <form class="list-head" onSubmit=${search}>
          <input class="input" style="flex:1" placeholder=${t("memory_search")} value=${query} onInput=${(e) => setQuery(e.target.value)} />
          <button class="btn">${t("search")}</button>
        </form>
        ${hits ? html`<div class="memory-group"><div class="label">${t("results")}</div>
          ${hits.map((h) => html`<button class="task-row" disabled=${!h.path.startsWith(prefix)} onClick=${() => openNote(h.path.slice(prefix.length))}>
            <span class="task-title">${h.link}</span><span class="faint">${h.score}</span>
            <span class="task-meta">${h.snippet.slice(0, 140)}</span></button>`)}
          ${hits.length ? null : html`<p class="muted">${t("no_results")}</p>`}</div>` : null}
        <div class="memory-group"><${PreferencesCard} toast=${toast} /></div>
        <div class="memory-group"><${DecisionsCard} toast=${toast} /></div>
        <div class="memory-group"><${ProfileCard} toast=${toast} /></div>
        ${info.pending.length ? html`<div class="memory-group"><div class="label">${t("learn")}</div>
          ${info.pending.map((p) => p.facts.map((f, i) => f.status === "proposed" ? html`<div class="card fact">
            <div>${f.fact}</div><div class="faint">${p.project} · ${p.prompt}</div>
            <div class="row"><button class="btn primary" onClick=${() => decide(p.task_id, [i], [])}>${t("remember")}</button>
              <button class="btn ghost" onClick=${() => decide(p.task_id, [], [i])}>${t("forget")}</button></div></div>` : null))}</div>` : null}
        ${groups.map(([kind, notes]) => html`<div class="memory-group"><div class="label">${t(`notes_${kind}`)}</div>
          ${notes.slice(0, kind === "journal" ? 14 : 200).map((n) => html`<button class="task-row ${note?.path === n.path ? "active" : ""}" onClick=${() => openNote(n.path)}>
            <span class="task-title">${n.title}</span><span class="faint">${ago(n.modified)}</span></button>`)}</div>`)}
      </div>
      <${VSplitter} width=${listW} setWidth=${setListW} commit=${commitListW} min=${260} max=${560} def=${360} />
      ${note ? html`<div class="detail note-editor">
        <button class="btn ghost back" onClick=${() => setNote(null)}>← ${t("memory")}</button>
        <div class="row"><strong>${note.path}</strong><span class="spacer"></span>
          <button class="btn primary" disabled=${text === note.text} onClick=${save}>${t("save")}</button></div>
        <textarea class="textarea mono" value=${text} onInput=${(e) => setText(e.target.value)}></textarea>
        <p class="faint">${t("memory_edit_help")}</p>
      </div>` : html`<div class="empty">${t("pick_note")}<br /><span class="faint">${info.describe}</span></div>`}
    </div>`;
}
