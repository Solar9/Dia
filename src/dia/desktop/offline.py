"""The page Dia's window shows while the backend does not answer (DIA-53).

It draws the window's own title bar when the system's is off, takes the colours of the
current theme, and says which of four states Dia is in: starting, stopped, failed to
start, or not set up. The window pushes a state change into the open page
(``diaOfflineState``) instead of reloading it, so nothing flickers."""

from __future__ import annotations

import base64
import json
import re

STATES = ("starting", "stopped", "error", "missing")

# Words per language: the fields of each state, and the buttons. English is the fallback.
_EN = {
    "starting": ("Dia is starting…", "This window opens as soon as Dia answers."),
    "stopped": ("Dia is stopped", "Start Dia to use it. The tray and the widget can manage the services too."),
    "error": ("Dia could not start", "The service ended with an error. Read the logs, then start it again."),
    "missing": ("Dia's service is not set up", "Starting Dia from here sets up its background service first."),
    "start": "Start Dia", "logs": "Show logs",
    "min": "Minimize", "max": "Maximize", "close": "Close",
}  # fmt: skip
WORDS: dict[str, dict] = {
    "en": _EN,
    "pl": {
        "starting": ("Dia się uruchamia…", "To okno otworzy się, gdy tylko Dia odpowie."),
        "stopped": ("Dia jest zatrzymana", "Uruchom Dia, żeby z niej korzystać. Usługami możesz zarządzać też z traya i widgetu."),
        "error": ("Dia nie mogła się uruchomić", "Usługa zakończyła się błędem. Zobacz logi i uruchom ją ponownie."),
        "missing": ("Usługa Dia nie jest skonfigurowana", "Uruchomienie Dia stąd najpierw skonfiguruje jej usługę w tle."),
        "start": "Uruchom Dia", "logs": "Pokaż logi",
        "min": "Minimalizuj", "max": "Maksymalizuj", "close": "Zamknij",
    },
    "de": {
        "starting": ("Dia startet…", "Dieses Fenster öffnet sich, sobald Dia antwortet."),
        "stopped": ("Dia ist gestoppt", "Starte Dia, um sie zu benutzen. Tray und Widget können die Dienste ebenfalls verwalten."),
        "error": ("Dia konnte nicht starten", "Der Dienst wurde mit einem Fehler beendet. Sieh in die Protokolle und starte ihn neu."),
        "missing": ("Dias Dienst ist nicht eingerichtet", "Beim Start von hier wird zuerst ihr Hintergrunddienst eingerichtet."),
        "start": "Dia starten", "logs": "Protokolle anzeigen",
        "min": "Minimieren", "max": "Maximieren", "close": "Schließen",
    },
    "fr": {
        "starting": ("Dia démarre…", "Cette fenêtre s'ouvrira dès que Dia répondra."),
        "stopped": ("Dia est arrêtée", "Démarrez Dia pour l'utiliser. La barre d'état et le widget peuvent aussi gérer les services."),
        "error": ("Dia n'a pas pu démarrer", "Le service s'est terminé avec une erreur. Consultez les journaux, puis relancez-le."),
        "missing": ("Le service de Dia n'est pas configuré", "Démarrer Dia d'ici configure d'abord son service d'arrière-plan."),
        "start": "Démarrer Dia", "logs": "Afficher les journaux",
        "min": "Réduire", "max": "Agrandir", "close": "Fermer",
    },
    "es": {
        "starting": ("Dia se está iniciando…", "Esta ventana se abrirá en cuanto Dia responda."),
        "stopped": ("Dia está detenida", "Inicia Dia para usarla. La bandeja y el widget también pueden gestionar los servicios."),
        "error": ("Dia no pudo iniciarse", "El servicio terminó con un error. Mira los registros y vuelve a iniciarlo."),
        "missing": ("El servicio de Dia no está configurado", "Iniciar Dia desde aquí configura primero su servicio en segundo plano."),
        "start": "Iniciar Dia", "logs": "Mostrar registros",
        "min": "Minimizar", "max": "Maximizar", "close": "Cerrar",
    },
    "it": {
        "starting": ("Dia si sta avviando…", "Questa finestra si aprirà non appena Dia risponde."),
        "stopped": ("Dia è ferma", "Avvia Dia per usarla. Anche l'area di notifica e il widget possono gestire i servizi."),
        "error": ("Dia non è riuscita ad avviarsi", "Il servizio è terminato con un errore. Guarda i log, poi riavvialo."),
        "missing": ("Il servizio di Dia non è configurato", "Avviare Dia da qui configura prima il suo servizio in background."),
        "start": "Avvia Dia", "logs": "Mostra i log",
        "min": "Riduci a icona", "max": "Ingrandisci", "close": "Chiudi",
    },
    "pt": {
        "starting": ("A Dia está iniciando…", "Esta janela abre assim que a Dia responder."),
        "stopped": ("A Dia está parada", "Inicie a Dia para usá-la. A bandeja e o widget também podem gerenciar os serviços."),
        "error": ("A Dia não conseguiu iniciar", "O serviço terminou com um erro. Veja os logs e inicie de novo."),
        "missing": ("O serviço da Dia não está configurado", "Iniciar a Dia daqui configura primeiro o serviço em segundo plano."),
        "start": "Iniciar a Dia", "logs": "Mostrar logs",
        "min": "Minimizar", "max": "Maximizar", "close": "Fechar",
    },
}  # fmt: skip

# The state of Dia's systemd unit (runtime.STATE_LABELS keys) as the window shows it.
_STATE_OF_UNIT = {
    "active": "starting",  # running, but the API does not answer yet
    "activating": "starting",
    "deactivating": "stopped",
    "inactive": "stopped",
    "failed": "error",
    "missing": "missing",
    "unknown": "stopped",
}


def offline_state(unit: dict | None) -> str:
    """Which of STATES to show for ``runtime.status()["dia"]`` (None: nothing known yet)."""
    if not unit:
        return "starting"
    return _STATE_OF_UNIT.get(unit.get("state", "unknown"), "stopped")


# The theme variables the page uses, with the colours it had before themes (Grafit).
_DEFAULTS = {
    "bg": "#131317", "bg-hover": "#1f1f25", "border": "#26262d", "text": "#ececf1",
    "text-muted": "#a1a1aa", "accent": "#b4a2ff", "accent-text": "#17131f",
    "ok": "#7ad9a6", "warn": "#f2b55a", "danger": "#f0868a", "font": "Inter, system-ui, sans-serif",
}  # fmt: skip
_SAFE = re.compile(r"^[#\w\s.,()%\"'-]{1,160}$")


def theme_css(variables: dict[str, str] | None) -> str:
    """``:root`` declarations from a theme's variables; unsafe values fall back to the default."""
    chosen = {**_DEFAULTS}
    for key in _DEFAULTS:
        value = (variables or {}).get(key, "")
        if value and _SAFE.fullmatch(value) and "url(" not in value.lower():
            chosen[key] = value.strip()
    return "".join(f"--{key}:{value};" for key, value in chosen.items())


PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
:root { __VARS__ }
html, body { height: 100%; margin: 0; }
body { background: var(--bg); color: var(--text); font: 14px/1.5 var(--font);
  display: flex; flex-direction: column; user-select: none; }
.bar { display: flex; align-items: center; gap: 10px; height: 52px; padding: 0 8px 0 20px;
  border-bottom: 1px solid var(--border); }
.brand { display: flex; align-items: center; gap: 10px; font-weight: 800; font-size: 18px;
  letter-spacing: -.03em; flex: 1; }
.brand img { width: 22px; height: 22px; }
.win { width: 44px; height: 36px; display: grid; place-items: center; border: 0; border-radius: 6px;
  background: none; color: var(--text-muted); cursor: pointer; }
.win:hover { background: var(--bg-hover); color: var(--text); }
.win.close:hover { background: #c42b1c; color: #fff; }
.win svg { width: 12px; height: 12px; fill: none; stroke: currentColor; stroke-width: 1.2; }
main { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 14px; padding: 32px; text-align: center; }
.dot { width: 10px; height: 10px; border-radius: 50%; --c: var(--warn); background: var(--c);
  box-shadow: 0 0 0 6px color-mix(in srgb, var(--c) 16%, transparent); }
[data-state="starting"] .dot { animation: pulse 1.6s infinite; }
[data-state="stopped"] .dot, [data-state="missing"] .dot { --c: var(--text-muted); }
[data-state="error"] .dot { --c: var(--danger); }
@keyframes pulse { 50% { opacity: .45; } }
h1 { margin: 0; font-size: 22px; font-weight: 600; }
p { margin: 0; color: var(--text-muted); max-width: 460px; }
.actions { display: flex; gap: 10px; }
button.btn { height: 40px; padding: 0 18px; border-radius: 8px; font: 600 14px var(--font); cursor: pointer;
  border: 1px solid var(--border); background: none; color: var(--text); }
button.btn.primary { border: 0; background: var(--accent); color: var(--accent-text); }
[data-state="starting"] .primary { display: none; }
[data-state="stopped"] .logs, [data-state="missing"] .logs, [data-state="starting"] .logs { display: none; }
.edge { position: fixed; z-index: 10; }
.maximized .edge { display: none; }
</style></head><body data-state="__STATE__">
<div class="bar" data-drag>
<span class="brand"><img src="__ICON__" alt="">dia</span>__CONTROLS__</div>
<main role="status" aria-live="polite"><span class="dot"></span><h1></h1><p></p>
<div class="actions"><button class="btn primary" onclick="console.log('dia-window:start-services')"></button>
<button class="btn logs" onclick="console.log('dia-window:show-logs')"></button></div></main>
__EDGES__
<script>
const WORDS = __WORDS__;
const call = (action) => console.log("dia-window:" + action);
window.diaOfflineState = (state) => {
  if (!WORDS[state]) return;
  document.body.dataset.state = state;
  document.querySelector("h1").textContent = WORDS[state][0];
  document.querySelector("p").textContent = WORDS[state][1];
  document.querySelector(".primary").textContent = WORDS.start;
  document.querySelector(".logs").textContent = WORDS.logs;
};
window.diaOfflineState("__STATE__");
document.addEventListener("mousedown", (e) => {
  if (e.button !== 0) return;
  const edge = e.target.closest("[data-edge]");
  if (edge) { e.preventDefault(); call("resize:" + edge.dataset.edge); return; }
  if (!e.target.closest("[data-drag]") || e.target.closest("button")) return;
  e.preventDefault();
  call("move");
});
document.addEventListener("dblclick", (e) => {
  if (e.target.closest("[data-drag]") && !e.target.closest("button")) call("maximize");
});
window.diaWindowState = (state) =>
  document.documentElement.classList.toggle("maximized", state === "maximized");
</script></body></html>"""
CONTROLS = (
    '<button class="win" title="__MIN__" aria-label="__MIN__" onclick="call(\'minimize\')">'
    '<svg viewBox="0 0 12 12"><path d="M2 6.5h8"/></svg></button>'
    '<button class="win" title="__MAX__" aria-label="__MAX__" onclick="call(\'maximize\')">'
    '<svg viewBox="0 0 12 12"><path d="M2.5 2.5h7v7h-7z"/></svg></button>'
    '<button class="win close" title="__CLOSE__" aria-label="__CLOSE__" onclick="call(\'close\')">'
    '<svg viewBox="0 0 12 12"><path d="M2.5 2.5l7 7M9.5 2.5l-7 7"/></svg></button>'
)
EDGES = {
    "top": "top:0;left:8px;right:8px;height:4px;cursor:ns-resize",
    "bottom": "bottom:0;left:8px;right:8px;height:4px;cursor:ns-resize",
    "left": "left:0;top:8px;bottom:8px;width:4px;cursor:ew-resize",
    "right": "right:0;top:8px;bottom:8px;width:4px;cursor:ew-resize",
    "top-left": "top:0;left:0;width:8px;height:8px;cursor:nwse-resize",
    "bottom-right": "bottom:0;right:0;width:8px;height:8px;cursor:nwse-resize",
    "top-right": "top:0;right:0;width:8px;height:8px;cursor:nesw-resize",
    "bottom-left": "bottom:0;left:0;width:8px;height:8px;cursor:nesw-resize",
}


def render(
    language: str,
    frameless: bool,
    icon_svg: bytes,
    variables: dict[str, str] | None = None,
    state: str = "starting",
) -> str:
    """The page. ``icon_svg`` is inlined: while Dia is stopped nothing serves /static/icons."""
    words = WORDS.get(language, WORDS["en"])
    state = state if state in STATES else "starting"
    edges = "".join(
        f'<div class="edge" data-edge="{name}" style="{style}"></div>'
        for name, style in EDGES.items()
    )
    page = PAGE.replace("__CONTROLS__", CONTROLS if frameless else "")
    page = page.replace("__EDGES__", edges if frameless else "")
    page = page.replace("__VARS__", theme_css(variables))
    page = page.replace(
        "__ICON__", "data:image/svg+xml;base64," + base64.b64encode(icon_svg).decode()
    )
    page = page.replace("__MIN__", words["min"]).replace("__MAX__", words["max"])
    page = page.replace("__CLOSE__", words["close"])
    page = page.replace("__WORDS__", json.dumps(words, ensure_ascii=False).replace("</", "<\\/"))
    return page.replace("__STATE__", state)
