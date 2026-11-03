import { html } from "../html.js";
import { Code, languageOf } from "./code.js";

// Text with ```fenced``` code blocks shown as highlighted code.
// Markdown as agents write it, drawn as elements (never as HTML from the text):
// paragraphs, headings, lists, tables, **bold**, *italic*, `code`, [links](https://…)
// and ```fenced code```.
export const INLINE = /(`[^`\n]+`)|(\*\*[^*\n]+?\*\*|__[^_\n]+?__)|(\[[^\]\n]+\]\((https?:\/\/[^)\s]+)\))|(\*[^*\s][^*\n]*?\*)/g;

export function inline(text) {
  const out = [];
  let last = 0;
  for (const m of text.matchAll(INLINE)) {
    if (m.index > last) out.push(text.slice(last, m.index));
    if (m[1]) out.push(html`<code class="inline">${m[1].slice(1, -1)}</code>`);
    else if (m[2]) out.push(html`<strong>${inline(m[2].slice(2, -2))}</strong>`);
    else if (m[3]) out.push(html`<a href=${m[4]} target="_blank" rel="noopener noreferrer">${m[3].slice(1, m[3].indexOf("]("))}</a>`);
    else out.push(html`<em>${m[5].slice(1, -1)}</em>`);
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export const cells = (line) => line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());

export function blocks(text) {
  const lines = text.split("\n");
  const out = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }
    if (/^\s*\|.*\|\s*$/.test(line) && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1] || "")) {
      const head = cells(line);
      const rows = [];
      for (i += 2; i < lines.length && /^\s*\|/.test(lines[i]); i++) rows.push(cells(lines[i]));
      out.push(html`<div class="md-table"><table><thead><tr>${head.map((c) => html`<th>${inline(c)}</th>`)}</tr></thead>
        <tbody>${rows.map((r) => html`<tr>${r.map((c) => html`<td>${inline(c)}</td>`)}</tr>`)}</tbody></table></div>`);
      continue;
    }
    const heading = line.match(/^\s*#{1,4}\s+(.*)$/);
    if (heading) { out.push(html`<div class="md-h">${inline(heading[1])}</div>`); i++; continue; }
    const bullet = /^\s*[-*•]\s+/, number = /^\s*\d+[.)]\s+/;
    if (bullet.test(line) || number.test(line)) {
      const ordered = number.test(line);
      const items = [];
      for (; i < lines.length && (ordered ? number : bullet).test(lines[i]); i++) items.push(lines[i].replace(ordered ? number : bullet, ""));
      const list = items.map((item) => html`<li>${inline(item)}</li>`);
      out.push(ordered ? html`<ol>${list}</ol>` : html`<ul>${list}</ul>`);
      continue;
    }
    const para = [];
    for (; i < lines.length && lines[i].trim() && !bullet.test(lines[i]) && !number.test(lines[i])
      && !/^\s*#{1,4}\s/.test(lines[i]) && !(/^\s*\|/.test(lines[i]) && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1] || "")); i++) para.push(lines[i]);
    out.push(html`<p>${para.flatMap((l, k) => (k ? [html`<br />`, ...inline(l)] : inline(l)))}</p>`);
  }
  return out;
}

export function RichText({ text, class: cls = "card prose", style }) {
  const parts = (text || "").split(/```([\w+#.-]*)[^\n]*\n([\s\S]*?)```/g);
  const out = [];
  for (let i = 0; i < parts.length; i += 3) {
    out.push(...blocks(parts[i]));
    if (i + 2 < parts.length) {
      out.push(html`<pre class="code mono"><${Code} code=${parts[i + 2].replace(/\n$/, "")} lang=${languageOf(parts[i + 1])} /></pre>`);
    }
  }
  return html`<div class=${`${cls} md`} style=${style}>${out}</div>`;
}
