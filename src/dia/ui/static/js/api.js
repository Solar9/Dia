import { store } from "./util.js";

export const TOKEN_KEY = "dia-token";

// Inside the Android/iOS app (mobile/): its pairing screen, to switch to another Dia.
export const IN_APP = navigator.userAgent.includes("DiaApp");

export const APP_HOME = /iPhone|iPad|iPod/.test(navigator.userAgent)
  ? "capacitor://localhost/index.html?reset=1" : "https://localhost/index.html?reset=1";

export let onPhone = false;

export function readToken() {
  const match = location.hash.match(/token=([^&]+)/);
  if (match) {
    store(TOKEN_KEY, decodeURIComponent(match[1]));
    history.replaceState(null, "", location.pathname);
  }
  return store(TOKEN_KEY) || "";
}

export let token = readToken();

export async function api(path, { method = "GET", body, raw } = {}) {
  const response = await fetch(path, {
    method,
    headers: { Authorization: `Bearer ${token}`, ...(body ? { "Content-Type": "application/json" } : {}),
      ...(raw ? { "Content-Type": raw.type } : {}) },
    body: raw || (body ? JSON.stringify(body) : undefined),
  });
  const type = response.headers.get("Content-Type") || "";
  const data = type.includes("json") ? await response.json() : await response.text();
  if (!response.ok) throw new Error((data && data.error) || data || response.statusText);
  return data;
}

export function setToken(value) {
  token = value;
}

export function setOnPhone(value) {
  onPhone = value;
}
