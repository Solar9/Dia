"""Local lifecycle control shared by the desktop, CLI and Plasma widget.

Only named Dia units and Ollama are controllable. No backend connection is needed.
Login starts the desktop launcher; legacy default.target links are removed when
applying a policy, so disabling login really disables every Dia entry point.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from dia.core.jsonfile import write_json
from dia.desktop import desktop, service

TARGET = "dia-session.target"
WARMUP = "dia-local-brain-warmup.service"
MODES = ("with-dia", "independent", "manual")


def policy_path() -> Path:
    return service._config_home() / "dia" / "startup.json"


def policy() -> dict:
    path = policy_path()
    if path.exists():
        return json.loads(path.read_text())
    return {"autostart": desktop.state()["autostart"], "ollama": "with-dia", "warmup": True}


def ctl(*args: str, system: bool = False, check: bool = True) -> str:
    command = ["systemctl", *([] if system else ["--user"]), *args]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=90)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"Service control failed: {exc}") from exc
    if check and result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip() or "systemctl failed")
    return result.stdout.strip()


# One vocabulary for a service's state, shared by the tray, the Plasma widget and the web
# UI (DIA-48). Keys are systemd's ActiveState; ``load == not-found`` is "missing".
STATE_LABELS: dict[str, dict[str, str]] = {
    "active": {
        "en": "Running",
        "pl": "Działa",
        "de": "Läuft",
        "fr": "En marche",
        "es": "En ejecución",
        "it": "In esecuzione",
        "pt": "Em execução",
    },
    "inactive": {
        "en": "Stopped",
        "pl": "Zatrzymana",
        "de": "Gestoppt",
        "fr": "Arrêté",
        "es": "Detenido",
        "it": "Fermo",
        "pt": "Parado",
    },
    "failed": {
        "en": "Error",
        "pl": "Błąd",
        "de": "Fehler",
        "fr": "Erreur",
        "es": "Error",
        "it": "Errore",
        "pt": "Erro",
    },
    "activating": {
        "en": "Starting…",
        "pl": "Uruchamia się…",
        "de": "Startet…",
        "fr": "Démarrage…",
        "es": "Iniciando…",
        "it": "Avvio…",
        "pt": "Iniciando…",
    },
    "deactivating": {
        "en": "Stopping…",
        "pl": "Zatrzymuje się…",
        "de": "Wird beendet…",
        "fr": "Arrêt…",
        "es": "Deteniendo…",
        "it": "Arresto…",
        "pt": "Parando…",
    },
    "missing": {
        "en": "Not installed",
        "pl": "Nie zainstalowano",
        "de": "Nicht installiert",
        "fr": "Non installé",
        "es": "No instalado",
        "it": "Non installato",
        "pt": "Não instalado",
    },
    "unknown": {
        "en": "Unknown",
        "pl": "Nieznany",
        "de": "Unbekannt",
        "fr": "Inconnu",
        "es": "Desconocido",
        "it": "Sconosciuto",
        "pt": "Desconhecido",
    },
}


VERB_LABELS: dict[str, dict[str, str]] = {
    "start": {
        "en": "Start",
        "pl": "Uruchom",
        "de": "Starten",
        "fr": "Démarrer",
        "es": "Iniciar",
        "it": "Avvia",
        "pt": "Iniciar",
    },
    "stop": {
        "en": "Stop",
        "pl": "Zatrzymaj",
        "de": "Stoppen",
        "fr": "Arrêter",
        "es": "Detener",
        "it": "Ferma",
        "pt": "Parar",
    },
    "restart": {
        "en": "Restart",
        "pl": "Uruchom ponownie",
        "de": "Neu starten",
        "fr": "Redémarrer",
        "es": "Reiniciar",
        "it": "Riavvia",
        "pt": "Reiniciar",
    },
}
# What happened to the last action (``service-operation.json``).
RESULT_LABELS: dict[str, dict[str, str]] = {
    "queued": {
        "en": "Scheduled",
        "pl": "Zaplanowano",
        "de": "Geplant",
        "fr": "Planifié",
        "es": "Programado",
        "it": "Pianificato",
        "pt": "Agendado",
    },
    "running": {
        "en": "In progress",
        "pl": "W toku",
        "de": "In Arbeit",
        "fr": "En cours",
        "es": "En curso",
        "it": "In corso",
        "pt": "Em andamento",
    },
    "done": {
        "en": "Done",
        "pl": "Gotowe",
        "de": "Fertig",
        "fr": "Terminé",
        "es": "Hecho",
        "it": "Fatto",
        "pt": "Concluído",
    },
    "failed": {
        "en": "Failed",
        "pl": "Nie udało się",
        "de": "Fehlgeschlagen",
        "fr": "Échec",
        "es": "Falló",
        "it": "Non riuscito",
        "pt": "Falhou",
    },
}
# Which verbs make sense in which state (DIA-49); every surface enables only these.
_VERBS_FOR = {
    "active": ["stop", "restart"],
    "inactive": ["start"],
    "failed": ["start", "restart"],
    "activating": ["stop"],
    "deactivating": [],
    "missing": [],
    "unknown": ["start"],
}


def allowed_verbs(load: str, active: str) -> list[str]:
    return list(_VERBS_FOR[state_key(load, active)])


def state_key(load: str, active: str) -> str:
    """The key into STATE_LABELS for a unit."""
    if load == "not-found":
        return "missing"
    return active if active in STATE_LABELS else "unknown"


def state_label(load: str, active: str, language: str = "en") -> str:
    words = STATE_LABELS[state_key(load, active)]
    return words.get(language, words["en"])


def unit_state(unit: str, *, system: bool = False) -> dict:
    out = ctl(
        "show", unit, "--property=LoadState,ActiveState,UnitFileState", system=system, check=False
    )
    fields = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    load = fields.get("LoadState", "not-found")
    active = fields.get("ActiveState", "unknown")
    key = state_key(load, active)
    return {
        "load": load,
        "active": active,
        "enabled": fields.get("UnitFileState", "unknown"),
        "state": key,
        "label": STATE_LABELS[key],
        "actions": allowed_verbs(load, active),
    }


def ollama_system() -> bool:
    # Preserve an existing user installation; never create a second server.
    return unit_state("ollama.service")["load"] == "not-found"


def status() -> dict:
    if not shutil.which("systemctl"):
        return {"available": False, "policy": policy()}
    system = ollama_system()
    return {
        "available": True,
        "policy": policy(),
        "dia": unit_state(service.UNIT_NAME),
        "warmup": unit_state(WARMUP),
        "ollama": {**unit_state("ollama.service", system=system), "system": system},
        "login_entry": desktop.state()["autostart"],
        "operation": _with_labels(operation()),
        "words": {"verbs": VERB_LABELS, "results": RESULT_LABELS},
    }


def _with_labels(op: dict | None) -> dict | None:
    if not op:
        return op
    return {**op, "label": RESULT_LABELS.get(op.get("state", ""), RESULT_LABELS["failed"])}


def prepare(config: Path | None, warmup: bool) -> None:
    if not service.installed():
        service.install(config, start=False, enable=False)
    root = service.unit_path().parent
    units = [service.UNIT_NAME]
    if unit_state(WARMUP)["load"] != "not-found":
        # Existing installations used a separate default.target warmup service.
        ctl("disable", WARMUP)
        if warmup:
            units.append(WARMUP)
    for unit in units:
        dropin = root / f"{unit}.d" / "dia-session.conf"
        dropin.parent.mkdir(parents=True, exist_ok=True)
        dropin.write_text(f"[Unit]\nPartOf={TARGET}\n")
    (root / TARGET).write_text(
        "[Unit]\nDescription=Dia background services\nWants=" + " ".join(units) + "\n"
    )
    ctl("daemon-reload")
    ctl("disable", service.UNIT_NAME)


def configure(config: Path | None, *, autostart: bool, ollama: str, warmup: bool) -> dict:
    if type(autostart) is not bool or type(warmup) is not bool or ollama not in MODES:
        raise ValueError("Invalid startup policy")
    if problem := service.check():
        raise RuntimeError(problem)
    system = ollama_system()
    if unit_state("ollama.service", system=system)["load"] != "not-found":
        # No --now: changing tomorrow's startup must not interrupt today's work.
        enabled = ollama == "independent" or (ollama == "with-dia" and autostart)
        ctl("enable" if enabled else "disable", "ollama.service", system=system)
    prepare(config, warmup)
    desktop.set_autostart(config, autostart)
    path = policy_path()
    write_json(
        path,
        {"autostart": autostart, "ollama": ollama, "warmup": warmup},
        indent=None,
        newline=True,
    )
    return status()


def action(component: str, verb: str, config: Path | None = None) -> None:
    if component not in ("dia", "ollama") or verb not in ("start", "stop", "restart"):
        raise ValueError("Unknown service action")
    if component == "ollama":
        ctl(verb, "ollama.service", system=ollama_system())
        return
    settings = policy()
    # Keep stopping independent from installation/configuration.
    if verb in ("start", "restart"):
        if not (service.unit_path().parent / TARGET).exists():
            prepare(config, settings["warmup"])
        if settings["ollama"] == "with-dia":
            system = ollama_system()
            if unit_state("ollama.service", system=system)["load"] != "not-found":
                ctl("start", "ollama.service", system=system)
    if verb == "stop":
        targets = [service.UNIT_NAME]
        if (service.unit_path().parent / TARGET).exists():
            targets.insert(0, TARGET)
        ctl("stop", *targets, *([WARMUP] if unit_state(WARMUP)["load"] != "not-found" else []))
        if settings["ollama"] == "with-dia":
            system = ollama_system()
            if unit_state("ollama.service", system=system)["load"] != "not-found":
                ctl("stop", "ollama.service", system=system)
    else:
        # Target Wants the local-brain warmup oneshot (TimeoutStartSec=300). Waiting
        # for it blocks the desktop/tray past ctl()'s 90s limit and surfaces a false
        # failure while Dia itself is already up — queue the job and return.
        ctl("--no-block", verb, TARGET)


def enqueue(component: str, verb: str, config: Path | None = None) -> None:
    """Move backend stop/restart out of its own cgroup before returning HTTP."""
    import sys
    import uuid

    if component not in ("dia", "ollama") or verb not in ("start", "stop", "restart"):
        raise ValueError("Unknown service action")
    report_operation(component, verb, "queued")
    command = [sys.executable, "-m", "dia"]
    if config:
        command += ["--config", str(config)]
    result = subprocess.run(
        [
            "systemd-run",
            "--user",
            "--collect",
            "--quiet",
            f"--unit=dia-control-{uuid.uuid4().hex}",
            "--on-active=1s",
            *command,
            "runtime",
            verb,
            component,
            "--report",
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode:
        report_operation(component, verb, "failed", result.stderr.strip())
        raise RuntimeError(result.stderr.strip() or "Could not schedule service action")


def logs(component: str) -> str:
    if component not in ("dia", "ollama"):
        raise ValueError("Unknown service")
    system = component == "ollama" and ollama_system()
    result = subprocess.run(
        [
            "journalctl",
            *([] if system else ["--user"]),
            "-u",
            f"{component}.service",
            "-n",
            "60",
            "--no-pager",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return result.stdout


def operation() -> dict | None:
    path = policy_path().with_name("service-operation.json")
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return None


def report_operation(component: str, verb: str, state: str, error: str = "") -> None:
    import time

    write_json(
        policy_path().with_name("service-operation.json"),
        {
            "component": component,
            "verb": verb,
            "state": state,
            "error": error,
            "at": time.time(),
        },
        indent=None,
        newline=True,
    )
