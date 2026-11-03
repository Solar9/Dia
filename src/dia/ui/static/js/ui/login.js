import { useState } from "preact/hooks";
import { html } from "../html.js";
import { t } from "../i18n.js";
import { DiaLogo } from "./logo.js";
import { FRAMELESS, WindowControls, WindowEdges } from "./window.js";

export function Login({ onToken }) {
  const [value, setValue] = useState("");
  const [error, setError] = useState("");
  const submit = (e) => {
    e.preventDefault();  // Enter in the field submits; an empty token is not sent anywhere
    const token = value.trim();
    if (!token) { setError(t("token_required")); return; }
    setError("");
    onToken(token);
  };
  return html`
    ${FRAMELESS ? html`<div class="login-bar" data-drag><span class="spacer"></span><${WindowControls} /></div><${WindowEdges} />` : null}
    <div class="login"><form class="card" onSubmit=${submit} noValidate>
      <div class="brand"><${DiaLogo} />Dia</div>
      <strong>${t("login_title")}</strong>
      <span class="muted" id="login-help">${t("login_help")}</span>
      <input class="input" type="password" name="token" autocomplete="off" autofocus spellcheck="false"
        placeholder=${t("token")} aria-label=${t("token")} aria-describedby="login-help"
        aria-invalid=${error ? "true" : undefined} value=${value}
        onInput=${(e) => { setValue(e.target.value); setError(""); }} />
      ${error ? html`<span class="login-error" role="alert">${error}</span>` : null}
      <button type="submit" class="btn primary">${t("connect")}</button>
    </form></div>`;
}
