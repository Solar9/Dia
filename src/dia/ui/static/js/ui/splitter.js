import { useRef, useState } from "preact/hooks";
import { html } from "../html.js";
import { t } from "../i18n.js";

/** Vertical drag handle. `reverse` when the sized pane sits to the right of the bar. */
export function VSplitter({ width, setWidth, commit, min, max, def, reverse = false }) {
  const live = useRef(width);
  live.current = width;
  const drag = useRef(null);
  const [active, setActive] = useState(false);
  const ceiling = () => Math.min(max, Math.floor(window.innerWidth * 0.55));
  const apply = (delta) => {
    const next = Math.min(ceiling(), Math.max(min, live.current + (reverse ? -delta : delta)));
    live.current = next;
    setWidth(next);
    return next;
  };

  const onPointerDown = (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { x: e.clientX, w: live.current };
    live.current = drag.current.w;
    setActive(true);
    document.body.classList.add("is-resizing");
  };
  const onPointerMove = (e) => {
    if (!drag.current) return;
    live.current = drag.current.w;
    apply(e.clientX - drag.current.x);
  };
  const end = () => {
    if (!drag.current) return;
    drag.current = null;
    setActive(false);
    document.body.classList.remove("is-resizing");
    commit(live.current);
  };
  const reset = () => {
    live.current = def;
    commit(def);
  };
  return html`<div class=${`vsplit${active ? " active" : ""}`} role="separator" aria-orientation="vertical"
    aria-valuenow=${Math.round(width)} aria-valuemin=${min} aria-valuemax=${max}
    aria-label=${t("split_resize")} title=${t("split_resize")} tabindex="0"
    onPointerDown=${onPointerDown} onPointerMove=${onPointerMove}
    onPointerUp=${end} onPointerCancel=${end} onDblClick=${reset}
    onKeyDown=${(e) => {
      const step = e.shiftKey ? 40 : 16;
      if (e.key === "ArrowLeft") { e.preventDefault(); commit(width + (reverse ? step : -step)); }
      if (e.key === "ArrowRight") { e.preventDefault(); commit(width + (reverse ? -step : step)); }
      if (e.key === "Home") { e.preventDefault(); reset(); }
    }} />`;
}
