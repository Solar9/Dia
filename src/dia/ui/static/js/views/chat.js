import { useEffect, useRef, useState } from "preact/hooks";
import { html } from "../html.js";
import { api } from "../api.js";
import { t } from "../i18n.js";
import { Icon } from "../ui/icons.js";
import { RichText } from "../ui/richtext.js";
import { confirmDialog, promptDialog } from "../ui/dialog.js";
import { ResourceState, useResource } from "../ui/resource.js";
import { VSplitter } from "../ui/splitter.js";
import { SPLIT_CHAT, dayKey, dayLabel, localeOf, parseWhen, stamp, store, useSplitWidth } from "../util.js";

export function MessageList({ messages, open, pendingPlan, send }) {
  let lastDay = "";
  return messages.map((m, i) => {
    const day = dayKey(m.at);
    const sep = Boolean(day) && day !== lastDay;
    if (day) lastDay = day;
    const mine = m.from === "me" || m.role === "user";
    const system = m.from === "system" || m.role === "system";
    return html`<div key=${`${day}-${i}`} class=${`msg-block ${system ? "is-system" : mine ? "is-me" : "is-dia"}`}>
      ${sep ? html`<div class="day-sep">${dayLabel(m.at)}</div>` : null}
      <div class=${`msg ${system ? "system" : mine ? "me" : "dia"}`}>
        <${RichText} text=${m.text} class="" />
        ${m.task && open ? html`<div class="chip"><button class="btn" onClick=${() => open(m.task)}>${t("open_task")}</button></div>` : null}
        ${m.plan && pendingPlan === m.plan && send ? html`<div class="chip row">
          <button class="btn primary" onClick=${() => send("yes", t("plan_yes"))}>${t("plan_yes")}</button>
          <button class="btn" onClick=${() => send("no", t("plan_no"))}>${t("plan_no")}</button></div>` : null}
        ${m.at ? html`<time class="msg-meta" datetime=${parseWhen(m.at)?.toISOString() || ""}>${stamp(m.at)}</time>` : null}
      </div>
    </div>`;
  });
}

export const SESSION_KEY = "dia-chat-session";

// A paired phone may not use the computer's microphone (docs/MOBILE.md), so it
// talks through its own: it records itself and sends the recording to Dia
// (/api/talk), whose own Whisper hears it and whose own voice answers. Without
// speech recognition on the computer, the browser's own recognition stands in.
export const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;

export const TALK_RATE = 16000;

export function wavOf(samples, rate) {
  const ratio = rate / TALK_RATE;
  const length = Math.floor(samples.length / ratio);
  const view = new DataView(new ArrayBuffer(44 + length * 2));
  const text = (at, word) => [...word].forEach((c, i) => view.setUint8(at + i, c.charCodeAt(0)));
  text(0, "RIFF"); view.setUint32(4, 36 + length * 2, true); text(8, "WAVE"); text(12, "fmt ");
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, TALK_RATE, true); view.setUint32(28, TALK_RATE * 2, true);
  view.setUint16(32, 2, true); view.setUint16(34, 16, true); text(36, "data"); view.setUint32(40, length * 2, true);
  for (let i = 0; i < length; i++) {
    // the average of the samples this one stands for: a simple low-pass before resampling
    let sum = 0, n = 0;
    for (let j = Math.floor(i * ratio); j < Math.floor((i + 1) * ratio) && j < samples.length; j++) { sum += samples[j]; n++; }
    const value = Math.max(-1, Math.min(1, n ? sum / n : 0));
    view.setInt16(44 + i * 2, value < 0 ? value * 0x8000 : value * 0x7fff, true);
  }
  return new Blob([view], { type: "audio/wav" });
}

// Records until the speaker stops (a pause after speech), at most 28 s; resolves
// with a 16 kHz mono WAV, or null when nobody spoke.
export async function recordSpeech(control) {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
  const ctx = new (window.AudioContext || window.webkitAudioContext)();
  const source = ctx.createMediaStreamSource(stream);
  const node = ctx.createScriptProcessor(4096, 1, 1);
  const chunks = [];
  let spoke = false, quiet = 0, total = 0, done = false;
  return new Promise((resolve) => {
    const finish = () => {
      if (done) return;
      done = true;
      control.stop = null;
      node.onaudioprocess = null;
      node.disconnect(); source.disconnect(); stream.getTracks().forEach((track) => track.stop()); ctx.close();
      if (!spoke) return resolve(null);
      const samples = new Float32Array(chunks.reduce((n, c) => n + c.length, 0));
      chunks.reduce((at, c) => { samples.set(c, at); return at + c.length; }, 0);
      resolve(wavOf(samples, ctx.sampleRate));
    };
    control.stop = finish;
    node.onaudioprocess = (e) => {
      const data = e.inputBuffer.getChannelData(0);
      chunks.push(new Float32Array(data));
      const seconds = data.length / ctx.sampleRate;
      const level = Math.sqrt(data.reduce((sum, x) => sum + x * x, 0) / data.length);
      total += seconds;
      if (level > 0.02) { spoke = true; quiet = 0; } else quiet += seconds;
      if ((spoke && quiet > 1.2) || total > 28 || (!spoke && total > 8)) finish();
    };
    source.connect(node); node.connect(ctx.destination);
  });
}

export function TalkSheet({ local, quiet, onClose, onType, open }) {
  const [mode, setMode] = useState(local ? "dia" : Recognition ? "browser" : "none");
  const [state, setState] = useState(mode === "none" ? "unsupported" : "idle");
  const [lines, setLines] = useState([]);
  const control = useRef({});
  const player = useRef(null);
  const end = useRef(null);
  useEffect(() => end.current?.scrollIntoView({ behavior: "smooth" }), [lines, state]);
  useEffect(() => () => { control.current.stop?.(); control.current.abort?.(); player.current?.pause(); window.speechSynthesis?.cancel(); }, []);
  const locale = localeOf();

  const browserSpeak = (text) => {
    if (quiet || !text || !window.speechSynthesis) { setState("idle"); return; }
    const say = new SpeechSynthesisUtterance(text);
    say.lang = locale;
    say.onend = say.onerror = () => setState("idle");
    setState("speaking");
    window.speechSynthesis.speak(say);
  };
  const play = (answer) => {
    if (!answer.audio) { browserSpeak(quiet ? "" : answer.reply); return; }
    const audio = player.current;
    audio.src = `data:${answer.audio_type};base64,${answer.audio}`;
    audio.onended = audio.onerror = () => setState("idle");
    setState("speaking");
    audio.play().catch(() => setState("idle"));
  };
  const said = (heard, answer) => {
    const at = Date.now() / 1000;
    setLines((all) => [...all, { from: "me", text: heard, at },
      { from: "dia", text: answer.reply || "", task: answer.task?.id || answer.plan?.id, at }]);
  };
  const failed = (e) => { setLines((all) => [...all, { from: "dia", text: `${t("failed")}: ${e.message}`, at: Date.now() / 1000 }]); setState("idle"); };
  const session = () => store(SESSION_KEY) || "owner";

  const listenWithDia = async () => {
    // a sound started by the tap itself lets the answer play later (autoplay rules)
    player.current = player.current || new Audio();
    player.current.src = URL.createObjectURL(wavOf(new Float32Array(1600), TALK_RATE));
    player.current.play().catch(() => {});
    let wav;
    try {
      setState("listening");
      wav = await recordSpeech(control.current);
    } catch (e) { setState("denied"); return; }
    if (!wav) { setState("unheard"); return; }
    setState("thinking");
    try {
      const answer = await api(`/api/talk?session=${encodeURIComponent(session())}`, { method: "POST", raw: wav });
      if (!answer.heard) { setState("unheard"); return; }
      said(answer.heard, answer);
      play(answer);
    } catch (e) {
      // no speech recognition on the computer (any more): the browser's own, where there is one
      if (Recognition && /whisper|stt|speech|install/i.test(e.message)) { setMode("browser"); setState("idle"); return; }
      failed(e);
    }
  };
  const listenWithBrowser = () => {
    const r = new Recognition();
    r.lang = locale;
    r.interimResults = false;
    let heard = "";
    r.onresult = (e) => { heard = Array.from(e.results).map((x) => x[0].transcript).join(" ").trim(); };
    r.onerror = () => {};
    r.onend = async () => {
      control.current.stop = null;
      if (!heard) { setState("unheard"); return; }
      setState("thinking");
      try {
        const answer = await api("/api/chat", { method: "POST", body: { text: heard, session: session() } });
        said(heard, answer);
        browserSpeak(answer.reply);
      } catch (e) { failed(e); }
    };
    control.current.stop = () => r.stop();
    control.current.abort = () => r.abort();
    setState("listening");
    r.start();
  };
  const tap = () => {
    if (state === "speaking") { player.current?.pause(); window.speechSynthesis?.cancel(); setState("idle"); return; }
    if (state === "listening") { control.current.stop?.(); return; }
    if (!["idle", "unheard", "denied"].includes(state)) return;
    (mode === "dia" ? listenWithDia : listenWithBrowser)();
  };
  const hint = { idle: t("talk_hint"), listening: t("talk_listening"), thinking: t("talk_thinking"),
    speaking: t("talk_speaking"), unheard: t("talk_unheard"), unsupported: t("talk_unsupported"), denied: t("talk_denied") }[state];

  return html`
    <div class="talk" role="dialog" aria-modal="true" aria-label=${t("talk_phone")}>
      <div class="talk-head"><span class="talk-title">${t("talk_phone")}${mode === "dia" ? html` · <span class="faint">${t("talk_local")}</span>` : null}</span>
        <button class="icon-btn" aria-label=${t("talk_end")} onClick=${onClose}><${Icon} name="close" /></button></div>
      <div class="talk-lines">
        ${lines.map((x) => html`<div class="talk-line ${x.from}">${x.text}
          ${x.at ? html`<time class="msg-meta">${stamp(x.at)}</time>` : null}
          ${x.task ? html`<button class="btn ghost" onClick=${() => open(x.task)}>${t("open_task")} <${Icon} name="arrow" size=${14} /></button>` : null}</div>`)}
        <span ref=${end}></span>
      </div>
      <div class="talk-orb-wrap">
        <button class="talk-orb ${state}" onClick=${tap} disabled=${state === "unsupported" || state === "thinking"}
          aria-label=${t("talk_mic")}><${Icon} name="mic" size=${30} /></button>
        <div class="talk-hint" aria-live="polite">${hint}</div>
      </div>
      <div class="talk-actions">
        <button class="btn" onClick=${onType}><${Icon} name="chat" size=${16} /> ${t("talk_type")}</button>
        <button class="btn ghost danger" onClick=${onClose}>${t("talk_end")}</button>
      </div>
    </div>`;
}

export function ChatView({ open, toast }) {
  const [sessions, setSessions] = useState([]);
  const [current, setCurrent] = useState(() => store(SESSION_KEY) || "owner");
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [showList, setShowList] = useState(false);
  const [providers, setProviders] = useState([]);
  const [listW, setListW, commitListW] = useSplitWidth(SPLIT_CHAT, 260, 180, 420);
  const end = useRef(null);
  const input = useRef(null);
  const grow = (el) => { el.style.height = "auto"; el.style.height = `${Math.min(el.scrollHeight, 160)}px`; };
  const providerRes = useResource("/api/chat/providers", { on: setProviders });
  useEffect(() => end.current?.scrollIntoView({ behavior: "smooth" }), [messages]);

  const loadSessions = () => api("/api/sessions").then(setSessions).catch((e) => toast(e.message, "error"));
  const loadMessages = (id) => api(`/api/sessions/${id}`).then((s) => setMessages(s.messages))
    .catch(() => { setCurrent("owner"); store(SESSION_KEY, "owner"); });
  useEffect(() => { loadSessions(); }, []);
  useEffect(() => { loadMessages(current); }, [current]);
  useEffect(() => {
    // a long task's answer is recorded when it finishes: show it then
    const onTask = (e) => { if (["done", "failed"].includes(e.detail.status)) loadMessages(current); };
    window.addEventListener("dia-task", onTask);
    return () => window.removeEventListener("dia-task", onTask);
  }, [current]);

  const choose = (id) => { setCurrent(id); store(SESSION_KEY, id); setShowList(false); };
  const create = async () => {
    try { const { id } = await api("/api/sessions", { method: "POST", body: {} }); await loadSessions(); choose(id); }
    catch (e) { toast(e.message, "error"); }
  };
  const rename = async (s) => {
    const title = await promptDialog(t("rename_prompt"), s.title || "");
    if (title === null) return;
    try { await api(`/api/sessions/${s.id}`, { method: "PATCH", body: { title } }); loadSessions(); }
    catch (e) { toast(e.message, "error"); }
  };
  const remove = async (s) => {
    if (!(await confirmDialog(s.main ? t("clear_main_confirm") : t("delete_session_confirm"), { danger: true }))) return;
    try {
      await api(`/api/sessions/${s.id}`, { method: "DELETE" });
      await loadSessions();
      if (s.id === current) { s.main ? loadMessages("owner") : choose("owner"); }
    } catch (e) { toast(e.message, "error"); }
  };

  const send = async (say, shown) => {  // `say` is what Dia is told, `shown` what the bubble reads
    const content = (say ?? text).trim();
    if (!content) return;
    setText("");
    if (input.current) input.current.style.height = "";
    setMessages((m) => [...m, { from: "me", text: shown || content, at: Date.now() / 1000 }]);
    setBusy(true);
    try {
      const answer = await api("/api/chat", { method: "POST", body: { text: content, session: current } });
      setMessages((m) => [...m, { from: "dia", text: answer.reply || "", task: answer.task?.id, plan: answer.plan?.id, at: Date.now() / 1000 }]);
      loadSessions();
      loadMessages(current);
    } catch (e) {
      setMessages((m) => [...m, { from: "dia", text: `${t("failed")}: ${e.message}`, at: Date.now() / 1000 }]);
    }
    setBusy(false);
  };

  const session = sessions.find((s) => s.id === current);
  const title = (s) => (s.main ? t("main_session") : s.title || t("untitled"));
  const provider = providers.find((p) => p.id === (session?.provider || "dia"));
  const setEngine = async (providerId, model) => {
    try {
      await api(`/api/sessions/${current}`, { method: "PATCH", body: { provider: providerId, model: model || "" } });
      loadSessions();
    } catch (e) { toast(e.message, "error"); }
  };
  return html`
    <div class="chat-split ${showList ? "show-list" : ""}" style=${{ "--chat-list-w": `${listW}px` }}>
      <div class="chat-sessions">
        <button class="btn primary" style="width:100%" onClick=${create}>+ ${t("new_session")}</button>
        <${ResourceState} res=${providerRes} quiet />
        ${sessions.map((s) => html`<div key=${s.id} class="session-row ${s.id === current ? "active" : ""}" onClick=${() => choose(s.id)}>
          <button type="button" class="session-open" aria-current=${s.id === current ? "true" : undefined} onClick=${(e) => { e.stopPropagation(); choose(s.id); }}>
            ${s.provider && s.provider !== "dia" ? html`<span class="faint" title=${s.provider}>◆</span>` : null}
            <span class="session-title" title=${s.main ? t("main_session_help") : title(s)}>${title(s)}</span>
            ${s.pending_plan ? html`<span class="pill" title=${t("run_plan")}>?</span>` : null}
          </button>
          <span class="session-actions">
            ${s.main ? null : html`<button class="btn ghost" title=${t("rename")} aria-label=${t("rename")} onClick=${(e) => { e.stopPropagation(); rename(s); }}>✎</button>`}
            <button class="btn ghost" title=${t("delete_session")} aria-label=${t("delete_session")} onClick=${(e) => { e.stopPropagation(); remove(s); }}>×</button>
          </span></div>`)}
      </div>
      <${VSplitter} width=${listW} setWidth=${setListW} commit=${commitListW} min=${180} max=${420} def=${260} />
      <div class="chat">
        <div class="chat-head"><button class="btn ghost sessions-toggle" onClick=${() => setShowList(!showList)}>☰ ${t("sessions")}</button>
          <strong style="flex:1">${session ? title(session) : ""}</strong>
          ${session && !session.main && providers.length > 1 ? html`<span class="chat-engine" title=${t("provider_help")}>
            <select class="select" value=${session.provider || "dia"} onChange=${(e) => setEngine(e.target.value, "")}>
              ${providers.map((p) => html`<option value=${p.id}>${p.label}</option>`)}</select>
            ${provider && provider.models.length ? html`<select class="select" value=${session.model || provider.models[0]}
              onChange=${(e) => setEngine(provider.id, e.target.value)}>
              ${provider.models.map((m) => html`<option value=${m}>${m === "default" ? t("default_model") : m}</option>`)}</select>` : null}
          </span>` : null}</div>
        <div class="messages">
          ${messages.length ? null : html`<div class="empty">${t("chat_hint")}</div>`}
          <${MessageList} messages=${messages} open=${open} pendingPlan=${session?.pending_plan} send=${send} />
          ${busy ? html`<div class="msg-block is-dia"><div class="msg dia pending" role="status" aria-live="polite">
            <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span> ${t("chat_thinking")}</div></div>` : null}
          <div ref=${end}></div>
        </div>
        <div class="chat-input">
          <textarea ref=${input} class="input chat-text" rows="1" placeholder=${t("chat_hint")} aria-label=${t("chat_hint")}
            value=${text} disabled=${busy}
            onInput=${(e) => { setText(e.target.value); grow(e.target); }}
            onKeyDown=${(e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); } }}></textarea>
          <button class="btn primary" disabled=${busy || !text.trim()} onClick=${() => send()}>${t("send")}</button>
        </div>
      </div>
    </div>`;
}
