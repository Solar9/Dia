import { useEffect, useState } from "preact/hooks";
import { html } from "../html.js";
import { t } from "../i18n.js";

// In Dia's own window (Qt, without the system frame) the page is the title bar:
// the sidebar's top and the top bar drag the window, a double click maximizes it,
// the edges resize it, and the three buttons sit at the top right. The window
// hears it through console messages (see dia/appwindow.py).
export const FRAMELESS = navigator.userAgent.includes("DiaDesktop/frameless");

export const windowCall = (action) => console.log(`dia-window:${action}`);

export const NOT_DRAG = "button, a, input, select, textarea, label, [data-no-drag]";

if (FRAMELESS) {
  document.documentElement.classList.add("frameless");
  let last = { at: 0, x: 0, y: 0 };
  document.addEventListener("mousedown", (e) => {
    if (e.button !== 0) return;
    const edge = e.target.closest("[data-edge]");
    if (edge) { e.preventDefault(); windowCall(`resize:${edge.dataset.edge}`); return; }
    if (!e.target.closest("[data-drag]") || e.target.closest(NOT_DRAG)) return;
    e.preventDefault();
    const double = e.timeStamp - last.at < 400 && Math.abs(e.screenX - last.x) < 4 && Math.abs(e.screenY - last.y) < 4;
    last = double ? { at: 0, x: 0, y: 0 } : { at: e.timeStamp, x: e.screenX, y: e.screenY };
    windowCall(double ? "maximize" : "move");
  });
}

export function WindowControls() {
  const [maximized, setMaximized] = useState(false);
  useEffect(() => {
    window.diaWindowState = (state) => {
      setMaximized(state === "maximized");
      document.documentElement.classList.toggle("maximized", state === "maximized");
    };
  }, []);
  if (!FRAMELESS) return null;
  return html`<div class="win-controls" data-no-drag>
    <button class="win-btn" title=${t("win_minimize")} onClick=${() => windowCall("minimize")}>
      <svg viewBox="0 0 12 12"><path d="M2 6.5h8" /></svg></button>
    <button class="win-btn" title=${t(maximized ? "win_restore" : "win_maximize")} onClick=${() => windowCall("maximize")}>
      ${maximized
        ? html`<svg viewBox="0 0 12 12"><path d="M3.5 4.5h4v4h-4z M5 4.5V3h4v4H7.5" /></svg>`
        : html`<svg viewBox="0 0 12 12"><path d="M2.5 2.5h7v7h-7z" /></svg>`}</button>
    <button class="win-btn close" title=${t("win_close")} onClick=${() => windowCall("close")}>
      <svg viewBox="0 0 12 12"><path d="M2.5 2.5l7 7M9.5 2.5l-7 7" /></svg></button>
  </div>`;
}

export const WindowEdges = () => (FRAMELESS ? html`<div class="edges">
  ${["top", "bottom", "left", "right", "top-left", "top-right", "bottom-left", "bottom-right"].map((edge) => html`<div class="edge edge-${edge}" data-edge=${edge}></div>`)}
</div>` : null);
