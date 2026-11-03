import { useEffect, useRef, useState } from "preact/hooks";
import { html } from "../html.js";
import { t } from "../i18n.js";
import { Code, languageOf } from "./code.js";
import { RichText } from "./richtext.js";

/** Split a unified diff into per-file patches (path, status, hunks, +/- counts). */
export function parseUnifiedDiff(text) {
  const files = [];
  let current = null;
  let oldLine = 0, newLine = 0;
  for (const raw of (text || "").split("\n")) {
    if (raw.startsWith("diff --git ")) {
      const parts = raw.slice("diff --git ".length).split(" ");
      const a = (parts[0] || "").replace(/^a\//, "");
      const b = (parts[1] || "").replace(/^b\//, "");
      current = {
        path: b || a || "?", oldPath: a || b || "?", status: "modified",
        lang: null, added: 0, removed: 0, binary: false, hunks: [],
      };
      files.push(current);
      continue;
    }
    if (!current) continue;
    if (raw.startsWith("new file mode")) { current.status = "added"; continue; }
    if (raw.startsWith("deleted file mode")) { current.status = "deleted"; continue; }
    if (raw.startsWith("rename from ")) { current.status = "renamed"; current.oldPath = raw.slice(12); continue; }
    if (raw.startsWith("rename to ")) { current.path = raw.slice(10); continue; }
    if (raw.startsWith("Binary files ") || raw.startsWith("GIT binary patch")) {
      current.binary = true;
      continue;
    }
    if (raw.startsWith("--- ")) {
      const p = raw.slice(4);
      if (p === "/dev/null") current.status = current.status === "renamed" ? current.status : "added";
      else current.oldPath = p.replace(/^a\//, "");
      continue;
    }
    if (raw.startsWith("+++ ")) {
      const p = raw.slice(4);
      if (p === "/dev/null") current.status = "deleted";
      else {
        current.path = p.replace(/^b\//, "");
        current.lang = languageOf(current.path);
      }
      continue;
    }
    if (raw.startsWith("@@")) {
      const m = raw.match(/@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
      oldLine = Number(m?.[1] || 0);
      newLine = Number(m?.[2] || 0);
      current.hunks.push({ header: raw, lines: [] });
      continue;
    }
    if (!current.hunks.length) continue;
    const hunk = current.hunks[current.hunks.length - 1];
    const sign = raw[0];
    if (sign === "+") {
      hunk.lines.push({ type: "add", oldLine: null, newLine: newLine++, text: raw.slice(1) });
      current.added += 1;
    } else if (sign === "-") {
      hunk.lines.push({ type: "del", oldLine: oldLine++, newLine: null, text: raw.slice(1) });
      current.removed += 1;
    } else if (sign === "\\") {
      hunk.lines.push({ type: "meta", oldLine: null, newLine: null, text: raw });
    } else {
      const textLine = sign === " " ? raw.slice(1) : raw;
      hunk.lines.push({ type: "ctx", oldLine: oldLine++, newLine: newLine++, text: textLine });
    }
  }
  for (const file of files) {
    if (!file.lang) file.lang = languageOf(file.path);
  }
  return files;
}

export function DiffFile({ file, notes, open, onToggle }) {
  const statusKey = {
    added: "diff_added_file", deleted: "diff_deleted_file",
    renamed: "diff_renamed_file", modified: "diff_modified_file",
  }[file.status] || "diff_modified_file";
  const rows = [];
  let rowKey = 0;
  for (const hunk of file.hunks) {
    rows.push(html`<div key=${`h-${rowKey++}`} class="diff-hunk" title=${hunk.header}>
      <span class="diff-ln"></span><span class="diff-ln"></span>
      <span class="sign"> </span><span class="diff-code">${hunk.header}</span></div>`);
    for (const line of hunk.lines) {
      const cls = line.type === "add" ? "add" : line.type === "del" ? "del" : line.type === "meta" ? "hunk" : "";
      const sign = line.type === "add" ? "+" : line.type === "del" ? "−" : " ";
      rows.push(html`<div key=${`l-${rowKey++}`} class=${`diff-row ${cls}`}>
        <span class="diff-ln">${line.oldLine ?? ""}</span>
        <span class="diff-ln">${line.newLine ?? ""}</span>
        <span class="sign">${sign}</span>
        <span class="diff-code"><${Code} code=${line.text || " "} lang=${file.lang} /></span>
      </div>`);
      if (line.type !== "del" && line.newLine != null) {
        notes.filter((n) => n.path === file.path && n.line === line.newLine).forEach((n, j) => {
          rows.push(html`<div key=${`n-${rowKey++}-${j}`} class="diff-note">
            <strong>${n.author}</strong><${RichText} text=${n.body} class="prose muted" /></div>`);
        });
      }
    }
  }
  const title = file.status === "renamed" && file.oldPath !== file.path
    ? `${file.oldPath} → ${file.path}` : file.path;
  return html`<section class="diff-file" data-diff-file=${file.path}>
    <button type="button" class="diff-file-head" aria-expanded=${open}
      title=${open ? t("diff_collapse") : t("diff_expand")} onClick=${onToggle}>
      <span class="diff-chevron" aria-hidden="true">${open ? "▾" : "▸"}</span>
      <span class="diff-path mono" title=${title}>${title}</span>
      <span class="diff-badge">${t(statusKey)}</span>
      <span class="spacer"></span>
      ${file.added || file.removed ? html`<span class="mono diff-stat">
        <span class="tone-ok">+${file.added}</span>
        <span class="tone-danger">−${file.removed}</span></span>` : null}
    </button>
    ${open ? html`<div class="diff-file-body mono">
      ${file.binary ? html`<div class="diff-binary faint">${t("diff_binary")}</div>`
        : rows.length ? rows : html`<div class="diff-binary faint">${t("diff_empty")}</div>`}
    </div>` : null}
  </section>`;
}

export function Diff({ text, notes = [], focusPath = null, onFocused }) {
  const files = parseUnifiedDiff(text);
  const [open, setOpen] = useState(() => Object.fromEntries(files.map((f) => [f.path, true])));
  const [active, setActive] = useState(files[0]?.path || "");
  const root = useRef(null);

  useEffect(() => {
    if (!focusPath || !root.current) return;
    setActive(focusPath);
    setOpen((prev) => ({ ...prev, [focusPath]: true }));
    const node = root.current.querySelector(`[data-diff-file="${CSS.escape(focusPath)}"]`);
    node?.scrollIntoView({ behavior: "smooth", block: "start" });
    onFocused?.();
  }, [focusPath]);

  if (text === "") return html`<div class="faint">${t("diff_empty")}</div>`;
  if (!files.length) {
    // Unusual payload without git headers: keep a readable fallback.
    return html`<pre class="diff mono">${text}</pre>`;
  }

  return html`<div class="diff-view" ref=${root}>
    <div class="diff-stack">
      ${files.map((f) => html`<${DiffFile} key=${f.path} file=${f} notes=${notes}
        open=${open[f.path] !== false}
        onToggle=${() => {
          setActive(f.path);
          setOpen((prev) => ({ ...prev, [f.path]: prev[f.path] === false }));
        }} />`)}
    </div>
  </div>`;
}
