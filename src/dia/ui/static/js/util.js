import { useCallback, useEffect, useState } from "preact/hooks";
import { lang, t } from "./i18n.js";
import { LOCALES } from "./lang/index.js";
import { paintIcon } from "./ui/logo.js";

export const clock = (iso) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

export const localeOf = () => LOCALES[lang] || "en-GB";

export function parseWhen(value) {
  if (value == null || value === "") return null;
  if (typeof value === "number") {
    const d = new Date(value < 1e12 ? value * 1000 : value);
    return Number.isNaN(d.getTime()) ? null : d;
  }
  const raw = String(value).trim();
  if (!raw) return null;
  if (/^\d+(\.\d+)?$/.test(raw)) {
    const n = Number(raw);
    const d = new Date(n < 1e12 ? n * 1000 : n);
    return Number.isNaN(d.getTime()) ? null : d;
  }
  const d = new Date(raw);
  if (!Number.isNaN(d.getTime())) return d;
  const d2 = new Date(raw.replace(/\s*\([^)]*\)\s*$/, ""));
  return Number.isNaN(d2.getTime()) ? null : d2;
}

export function stamp(value) {
  const d = parseWhen(value);
  if (!d) return "";
  return d.toLocaleString(localeOf(), {
    day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

export function dayKey(value) {
  const d = parseWhen(value);
  if (!d) return "";
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function dayLabel(value) {
  const d = parseWhen(value);
  if (!d) return "";
  const today = new Date();
  const yday = new Date(today);
  yday.setDate(today.getDate() - 1);
  if (d.toDateString() === today.toDateString()) return t("today");
  if (d.toDateString() === yday.toDateString()) return t("yesterday");
  return d.toLocaleDateString(localeOf(), { weekday: "long", day: "numeric", month: "long", year: "numeric" });
}

export const THEME_KEY = "dia-theme";

// a paired device: its own theme may differ from the app's
export const SIDEBAR_KEY = "dia-sidebar";

export const SPLIT_SIDEBAR = "dia-split-sidebar";

export const SPLIT_TASKS = "dia-split-tasks";

export const SPLIT_MISSIONS = "dia-split-missions";

export const SPLIT_MEMORY = "dia-split-memory";

export const SPLIT_CHAT = "dia-split-chat";

export const SPLIT_CLI = "dia-split-cli";

export const SPLIT_INBOX = "dia-split-inbox";

export const SPLIT_SETTINGS = "dia-split-settings";

export function store(key, value) {
  try {
    if (value === undefined) return localStorage.getItem(key);
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch (e) { /* storage may be unavailable; the UI still works */ }
  return value;
}

export function loadSplitWidth(key, fallback, min, max) {
  const n = Number(store(key));
  return Number.isFinite(n) ? Math.min(max, Math.max(min, n)) : fallback;
}

/** Remembered pane width + a vertical drag handle (like an IDE splitter). */
export function useSplitWidth(key, fallback, min, max) {
  const [width, setWidth] = useState(() => loadSplitWidth(key, fallback, min, max));
  const commit = useCallback((next) => {
    const clamped = Math.min(max, Math.max(min, Math.round(next)));
    setWidth(clamped);
    store(key, String(clamped));
    return clamped;
  }, [key, min, max]);
  return [width, setWidth, commit];
}

// What the address asks for (#token=...&view=chat&task=ID), read before the
// token is wiped from it: the desktop window and its tray open a given tab.
export const VIEWS = ["inbox", "tasks", "missions", "chat", "cli", "memory", "status", "usage", "settings"];

export const hashParam = (name) => (location.hash.match(new RegExp(`[#&]${name}=([\\w-]+)`)) || [])[1] || null;

export const START_VIEW = VIEWS.includes(hashParam("view")) ? hashParam("view") : null;

export const START_TASK = hashParam("task");

// "system" is not a file: it is dark or light as the system says, and follows it as it changes.
const SYSTEM = "system";
const systemLight = typeof matchMedia === "function" ? matchMedia("(prefers-color-scheme: light)") : null;
const resolveTheme = (name) => (name === SYSTEM ? (systemLight?.matches ? "light" : "dark") : name);
systemLight?.addEventListener?.("change", () => { if (store(THEME_KEY) === SYSTEM) applyTheme(SYSTEM); });

// The browser's and the PWA's bars take the theme's own background (<meta name="theme-color">).
function paintThemeColor() {
  const bg = getComputedStyle(document.documentElement).getPropertyValue("--bg").trim();
  if (bg) document.querySelector('meta[name="theme-color"]')?.setAttribute("content", bg);
}

export function applyTheme(name) {
  const link = document.getElementById("theme");
  const href = `/themes/${encodeURIComponent(resolveTheme(name))}.css`;
  store(THEME_KEY, name);
  const painted = () => { paintIcon(); paintThemeColor(); };
  if (link.getAttribute("href") === href) { painted(); return; }  // loaded with the page
  link.onload = painted;  // the new theme's accent colours Dia's icon and the bars
  link.href = href;
}

export const STATUS_ORDER = ["running", "waiting", "queued", "planned", "done", "failed", "published", "merged", "discarded"];

// Re-render every `ms`, so "running for 4m" keeps counting.
export function useTick(ms) {
  const [, set] = useState(0);
  useEffect(() => { const timer = setInterval(() => set((n) => n + 1), ms); return () => clearInterval(timer); }, [ms]);
}

export function ago(iso) {
  if (!iso) return "";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return `${Math.floor(s)}${t("unit_s")}`;
  if (s < 3600) return `${Math.floor(s / 60)}${t("unit_m")}`;
  if (s < 86400) return `${Math.floor(s / 3600)}${t("unit_h")}`;
  return `${Math.floor(s / 86400)}${t("unit_d")}`;
}

export const firstLine = (text) => (text || "").split("\n")[0];
