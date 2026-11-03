// The first thing on the Status page: five tiles with the state of Dia at a glance (DIA-63).
// The counts are the API's (dia.core.taskstate), the same as the badges, the tray and the widget.
import { html } from "../html.js";
import { lang, t } from "../i18n.js";
import { useResource } from "../ui/resource.js";

const tile = (key, label, value, tone, hint) => html`<div key=${key} class="summary-tile" title=${hint || ""}>
  <span class="summary-label">${label}</span>
  <span class="summary-value"><span class="dot ${tone}" aria-hidden="true"></span>${value}</span></div>`;

// ok / warn / danger / "" for how healthy the agents are as a whole
export function agentsTone(agents) {
  const ok = agents.filter((a) => a.ok && !a.limited_until).length;
  return agents.length && ok === agents.length ? "ok" : ok ? "warn" : "danger";
}

export function SummaryRow({ status }) {
  // How Dia runs: the systemd unit says so when there is one; started by hand, the page itself proves it runs.
  const desktop = useResource("/api/desktop", { interval: 15000 }).data;
  const unit = desktop?.runtime?.dia;
  const managed = unit && unit.state !== "missing" && unit.state !== "inactive";
  const service = managed ? (unit.label?.[lang] || unit.label?.en || unit.active) : t("svc_unmanaged");
  const serviceTone = !unit || !managed ? "ok" : unit.state === "active" ? "ok" : unit.state === "failed" ? "danger" : "warn";
  const agents = status.agents || [];
  const counts = status.counts || { running: 0, waiting_for_you: 0 };
  const sandbox = status.sandbox || "unavailable";
  return html`<div class="summary-row" role="group" aria-label=${t("status")}>
    ${tile("service", t("sum_service"), service, serviceTone)}
    ${tile("sandbox", t("sandbox"), t(sandbox === "on" ? "on" : sandbox === "off" ? "off" : "unavailable"),
      sandbox === "on" ? "ok" : "danger", t(`sandbox_${sandbox}`))}
    ${tile("agents", t("agents"), t("agents_ready", { ok: agents.filter((a) => a.ok).length, all: agents.length }), agentsTone(agents))}
    ${tile("running", t("running"), counts.running, counts.running ? "warn" : "ok")}
    ${tile("waiting", t("waiting_for_you"), counts.waiting_for_you, counts.waiting_for_you ? "warn" : "ok")}
  </div>`;
}
