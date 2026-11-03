// Our own confirm / prompt (DIA-58): the browser's native boxes look wrong in Dia's window, are
// blocked in some embedded views, and cannot be themed or translated. Both return a promise:
//   if (!(await confirmDialog("Delete it?", { danger: true }))) return;
//   const name = await promptDialog("Name:", "now"); // null when cancelled
// The dialog mounts itself the first time it is needed, so no view has to render it.
import { render } from "preact";
import { useEffect, useRef, useState } from "preact/hooks";
import { html } from "../html.js";
import { t } from "../i18n.js";

const queue = [];
let show = () => {};
let host = null;

function ask(spec) {
  if (!host) {
    host = document.createElement("div");
    host.id = "dialog-host";
    document.body.appendChild(host);
    render(html`<${DialogHost} />`, host);
  }
  return new Promise((resolve) => { queue.push({ ...spec, resolve }); show(); });
}

export const confirmDialog = (message, { danger = false, ok } = {}) =>
  ask({ kind: "confirm", message, danger, ok });

export const promptDialog = (message, initial = "", { ok } = {}) =>
  ask({ kind: "prompt", message, initial, ok });

function DialogHost() {
  const [, rerender] = useState(0);
  useEffect(() => { show = () => rerender((n) => n + 1); show(); return () => { show = () => {}; }; }, []);
  const item = queue[0];
  if (!item) return null;
  const done = (result) => { queue.shift(); item.resolve(result); show(); };
  return html`<${DialogBox} key=${item} item=${item} done=${done} />`;
}

const FOCUSABLE = "input, button:not([disabled])";

function DialogBox({ item, done }) {
  const prompting = item.kind === "prompt";
  const cancelled = prompting ? null : false;
  const [value, setValue] = useState(item.initial || "");
  const box = useRef(null);
  useEffect(() => {
    const before = document.activeElement;  // focus goes back where it was
    const first = prompting ? box.current.querySelector("input") : box.current.querySelector("[type=submit]");
    first?.focus();
    if (prompting) first?.select();
    return () => before?.focus?.();
  }, []);
  const key = (e) => {
    if (e.key === "Escape") { e.preventDefault(); done(cancelled); return; }
    if (e.key !== "Tab") return;  // keep Tab inside the dialog
    const items = [...box.current.querySelectorAll(FOCUSABLE)];
    const edge = e.shiftKey ? items[0] : items[items.length - 1];
    if (document.activeElement === edge) { e.preventDefault(); items[e.shiftKey ? items.length - 1 : 0].focus(); }
  };
  return html`<div class="dialog-backdrop" onMouseDown=${(e) => e.target === e.currentTarget && done(cancelled)} onKeyDown=${key}>
    <form class="dialog" ref=${box} role=${item.danger ? "alertdialog" : "dialog"} aria-modal="true" aria-labelledby="dialog-message"
      onSubmit=${(e) => { e.preventDefault(); done(prompting ? value : true); }}>
      <p id="dialog-message">${item.message}</p>
      ${prompting ? html`<input class="input" value=${value} aria-labelledby="dialog-message" onInput=${(e) => setValue(e.target.value)} />` : null}
      <div class="dialog-actions">
        <button type="button" class="btn ghost" onClick=${() => done(cancelled)}>${t("cancel")}</button>
        <button type="submit" class="btn ${item.danger ? "danger" : "primary"}">${item.ok || t("ok")}</button>
      </div>
    </form></div>`;
}
