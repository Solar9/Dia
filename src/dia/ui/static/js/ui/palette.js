import { useEffect, useRef, useState } from "preact/hooks";
import { html } from "../html.js";
import { t } from "../i18n.js";
import { Icon } from "./icons.js";
import { firstLine } from "../util.js";

export function Palette({ tasks, items, onClose, open }) {
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState(0);
  const input = useRef(null);
  useEffect(() => input.current?.focus(), []);
  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const matches = (text) => words.every((w) => text.toLowerCase().includes(w));
  const found = [
    ...items.filter((x) => matches(x.label)).map((x) => ({ ...x, kind: x.kind })),
    ...(words.length ? tasks.filter((x) => matches(`${x.prompt} ${x.id} ${x.branch || ""} ${x.project} ${x.agent}`)).slice(0, 8)
      .map((x) => ({ kind: "task", label: firstLine(x.prompt), hint: `${x.project} · ${x.status} · ${x.id}`, run: () => open(x.id) })) : []),
  ];
  const at = Math.min(index, Math.max(0, found.length - 1));
  const choose = (x) => { if (x) { onClose(); x.run(); } };
  const onKey = (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setIndex((at + 1) % Math.max(1, found.length)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setIndex((at - 1 + found.length) % Math.max(1, found.length)); }
    else if (e.key === "Enter") { e.preventDefault(); choose(found[at]); }
    else if (e.key === "Escape") { e.preventDefault(); onClose(); }
  };
  return html`<div class="palette-backdrop" onClick=${onClose}>
    <div class="palette" role="dialog" aria-modal="true" aria-label=${t("search")} onClick=${(e) => e.stopPropagation()}>
      <div class="palette-input"><${Icon} name="search" size=${17} />
        <input ref=${input} value=${query} placeholder=${t("palette_hint")} aria-label=${t("search")}
          role="combobox" aria-expanded="true" aria-controls="palette-list"
          onInput=${(e) => { setQuery(e.target.value); setIndex(0); }} onKeyDown=${onKey} />
        <kbd>Esc</kbd></div>
      <div class="palette-list" id="palette-list" role="listbox">
        ${found.length ? found.map((x, i) => html`<button role="option" aria-selected=${i === at} class="palette-item ${i === at ? "active" : ""}"
          onMouseEnter=${() => setIndex(i)} onClick=${() => choose(x)}>
          <${Icon} name=${x.icon || (x.kind === "task" ? "tasks" : "arrow")} size=${16} />
          <span class="palette-label">${x.label}</span><span class="faint">${x.hint || t(`kind_${x.kind}`)}</span></button>`)
          : html`<div class="palette-empty faint">${t("nothing_found")}</div>`}
      </div>
    </div></div>`;
}
