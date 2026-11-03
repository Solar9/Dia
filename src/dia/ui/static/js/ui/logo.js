import { html } from "../html.js";

// The rings of icons/dia.svg, their gradient made from the theme's accent:
// lighter, the accent itself, darker, darkest.
export const LOGO_MIX = [[0, 0.45, 255], [0.46, 1, 0], [0.72, 0.7, 0], [1, 0.35, 0]];

export function logoSvg(stops, id = "dia") {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><defs><linearGradient id="${id}" x1="0" y1="0" x2="1" y2="1">${
    stops.map(([offset, color]) => `<stop offset="${offset}" stop-color="${color}"/>`).join("")
  }</linearGradient></defs><circle cx="256" cy="256" r="208" fill="none" stroke="url(#${id})" stroke-width="54"/><circle cx="256" cy="256" r="112" fill="url(#${id})"/></svg>`;
}

export function DiaLogo({ class: cls = "brand-logo" }) {
  // live CSS colours: the icon follows a theme switch at once
  const stops = LOGO_MIX.map(([offset, share, other]) => [offset, share === 1 ? "var(--accent)"
    : `color-mix(in srgb, var(--accent) ${share * 100}%, ${other ? "white" : "black"})`]);
  return html`<svg class=${cls} viewBox="0 0 512 512" aria-hidden="true" dangerouslySetInnerHTML=${{
    __html: logoSvg(stops, "dia-logo").replace(/^<svg[^>]*>|<\/svg>$/g, "").replace(/stop-color="([^"]+)"/g, 'style="stop-color:$1"') }}></svg>`;
}

// The favicon, and in Dia's own window its window and tray icon, in the accent too.
export function paintIcon() {
  const probe = document.createElement("i");
  probe.style.color = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim();
  document.body.appendChild(probe);
  const rgb = (getComputedStyle(probe).color.match(/\d+/g) || []).slice(0, 3).map(Number);
  probe.remove();
  if (rgb.length !== 3) return;
  const hex = (c) => `#${c.map((v) => Math.round(v).toString(16).padStart(2, "0")).join("")}`;
  const stops = LOGO_MIX.map(([offset, share, other]) => [offset, hex(rgb.map((v) => v * share + other * (1 - share)))]);
  const svg = logoSvg(stops);
  document.querySelectorAll('link[rel="icon"]').forEach((link) => link.remove());
  const link = Object.assign(document.createElement("link"), { rel: "icon", type: "image/svg+xml",
    href: `data:image/svg+xml,${encodeURIComponent(svg)}` });
  document.head.appendChild(link);
  if (navigator.userAgent.includes("DiaDesktop")) console.log(`dia-window:accent:${hex(rgb).slice(1)}`);
}
