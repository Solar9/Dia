import { html } from "../html.js";

export const LANGUAGES = {
  gd: "gdscript", gdscript: "gdscript", py: "python", python: "python", cs: "csharp",
  csharp: "csharp", js: "javascript", mjs: "javascript", cjs: "javascript", jsx: "javascript",
  javascript: "javascript", ts: "typescript", tsx: "typescript", typescript: "typescript",
  rs: "rust", rust: "rust", toml: "toml", json: "json", md: "markdown", markdown: "markdown",
  sh: "bash", bash: "bash", shell: "bash", yml: "yaml", yaml: "yaml", ini: "ini", cfg: "ini",
  godot: "ini", tscn: "ini", tres: "ini", import: "ini", css: "css", html: "markup",
  xml: "markup", svg: "markup", c: "c", h: "c", cpp: "cpp", hpp: "cpp", cc: "cpp",
  java: "java", go: "go",
};

export function languageOf(nameOrPath) {
  const key = (nameOrPath || "").toLowerCase().split("/").pop().split(".").pop();
  const lang = LANGUAGES[key];
  return lang && window.Prism?.languages[lang] ? lang : null;
}

// Highlighted HTML for one piece of code; Prism escapes the text itself.
export function Code({ code, lang }) {
  if (!lang) return code || " ";
  return html`<span dangerouslySetInnerHTML=${{ __html: window.Prism.highlight(code, window.Prism.languages[lang], lang) }} />`;
}
