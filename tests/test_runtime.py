import pytest

from dia.desktop import desktop, runtime, service

LANGUAGES = {"en", "pl", "de", "fr", "es", "it", "pt"}  # the service words follow the UI languages


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(desktop, "desktop_dir", lambda: tmp_path / "Desktop")
    monkeypatch.setattr(service, "check", lambda: None)
    calls = []

    def ctl(*args, **kwargs):
        calls.append((args, kwargs))
        if args[0] == "show":
            if args[1] == "ollama.service" and not kwargs.get("system"):
                return "LoadState=not-found"
            return "LoadState=loaded\nActiveState=active\nUnitFileState=enabled"
        return ""

    monkeypatch.setattr(runtime, "ctl", ctl)
    monkeypatch.setattr(service, "installed", lambda: True)
    service.unit_path().parent.mkdir(parents=True)
    return calls


@pytest.mark.parametrize(
    "autostart,mode,enabled",
    [
        (False, "with-dia", False),
        (True, "with-dia", True),
        (False, "independent", True),
        (True, "manual", False),
    ],
)
def test_policy_reconciles_all_login_paths(manager, autostart, mode, enabled):
    runtime.configure(None, autostart=autostart, ollama=mode, warmup=True)
    assert (("enable" if enabled else "disable", "ollama.service"), {"system": True}) in manager
    assert (("disable", "dia.service"), {}) in manager
    assert (("disable", runtime.WARMUP), {}) in manager
    assert desktop.state()["autostart"] is autostart
    assert runtime.policy()["ollama"] == mode
    assert all("--now" not in args for args, _ in manager)
    target = service.unit_path().parent / runtime.TARGET
    assert runtime.WARMUP in target.read_text()


def test_disable_removes_existing_login_entry(manager):
    desktop.set_autostart(None, True)
    runtime.configure(None, autostart=False, ollama="manual", warmup=False)
    assert not desktop.state()["autostart"]
    assert runtime.WARMUP not in (service.unit_path().parent / runtime.TARGET).read_text()


def test_stop_keeps_independent_ollama(manager):
    runtime.configure(None, autostart=True, ollama="independent", warmup=False)
    manager.clear()
    runtime.action("dia", "stop")
    assert any(args[0] == "stop" and "dia.service" in args for args, _ in manager)
    assert not any(args[0] == "stop" and "ollama.service" in args for args, _ in manager)


def test_stop_also_stops_linked_ollama(manager):
    runtime.action("dia", "stop")
    assert (("stop", "ollama.service"), {"system": True}) in manager


def test_start_does_not_block_on_session_target(manager, tmp_path):
    (service.unit_path().parent / runtime.TARGET).write_text("[Unit]\nDescription=test\n")
    manager.clear()
    runtime.action("dia", "start")
    assert (("--no-block", "start", runtime.TARGET), {}) in manager


def test_restart_does_not_block_on_session_target(manager, tmp_path):
    (service.unit_path().parent / runtime.TARGET).write_text("[Unit]\nDescription=test\n")
    manager.clear()
    runtime.action("dia", "restart")
    assert (("--no-block", "restart", runtime.TARGET), {}) in manager


def test_failed_authorization_does_not_claim_policy_saved(manager, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("Access denied")

    monkeypatch.setattr(runtime, "ollama_system", lambda: True)
    monkeypatch.setattr(runtime, "unit_state", lambda *a, **k: {"load": "loaded"})
    monkeypatch.setattr(runtime, "ctl", fail)
    with pytest.raises(RuntimeError, match="Access denied"):
        runtime.configure(None, autostart=False, ollama="manual", warmup=False)
    assert not runtime.policy_path().exists()


def test_arbitrary_service_rejected(manager):
    with pytest.raises(ValueError):
        runtime.action("ssh", "stop")


def test_stop_legacy_installation_without_target(manager):
    runtime.action("dia", "stop")
    stop = next(args for args, _ in manager if args[0] == "stop")
    assert "dia.service" in stop and runtime.WARMUP in stop
    assert runtime.TARGET not in stop


def test_backend_action_runs_in_separate_unit_and_reports_result(manager, monkeypatch):
    from types import SimpleNamespace

    commands = []
    monkeypatch.setattr(
        runtime.subprocess,
        "run",
        lambda argv, **kw: commands.append(argv) or SimpleNamespace(returncode=0, stderr=""),
    )
    runtime.enqueue("dia", "restart")
    assert commands[0][0] == "systemd-run"
    assert commands[0][-4:] == ["runtime", "restart", "dia", "--report"]
    assert runtime.operation()["state"] == "queued"
    runtime.report_operation("dia", "restart", "failed", "Access denied")
    assert runtime.status()["operation"]["error"] == "Access denied"


def test_state_words_exist_in_both_languages_and_are_shared():
    # DIA-48: one vocabulary for tray, widget and web UI.
    assert set(runtime.STATE_LABELS) == {
        "active", "inactive", "failed", "activating", "deactivating", "missing", "unknown",
    }  # fmt: skip
    for words in runtime.STATE_LABELS.values():
        assert set(words) == LANGUAGES and all(words.values())
    assert runtime.state_label("loaded", "active", "pl") == "Działa"
    assert runtime.state_label("loaded", "active", "en") == "Running"
    assert runtime.state_label("not-found", "inactive", "en") == "Not installed"
    assert runtime.state_label("loaded", "weird", "pl") == "Nieznany"


def test_unit_state_carries_the_label(monkeypatch):
    monkeypatch.setattr(
        runtime,
        "ctl",
        lambda *a, **k: "LoadState=loaded\nActiveState=failed\nUnitFileState=enabled",
    )
    unit = runtime.unit_state("dia.service")
    assert unit["state"] == "failed"
    assert unit["label"]["en"] == "Error" and unit["label"]["pl"] == "Błąd"


def test_surfaces_do_not_keep_their_own_state_words():
    from pathlib import Path

    ui = Path(runtime.__file__).parents[1] / "ui"
    qml = (ui / "plasmoid/contents/ui/main.qml").read_text()
    web = (ui / "static/js/views/settings_devices.js").read_text()
    assert "Zatrzymana" not in qml and "Zatrzymana" not in web
    assert "unit.label" in qml and "state[c].label" in web


@pytest.mark.parametrize(
    ("load", "active", "verbs"),
    [
        ("loaded", "active", ["stop", "restart"]),
        ("loaded", "inactive", ["start"]),
        ("loaded", "failed", ["start", "restart"]),
        ("loaded", "activating", ["stop"]),
        ("loaded", "deactivating", []),
        ("not-found", "inactive", []),
    ],
)
def test_only_meaningful_verbs_are_offered(load, active, verbs):
    # DIA-49
    assert runtime.allowed_verbs(load, active) == verbs


def test_status_carries_verbs_results_and_labelled_operation(manager, monkeypatch):
    monkeypatch.setattr(runtime.shutil, "which", lambda _: "/usr/bin/systemctl")
    runtime.report_operation("dia", "restart", "failed", "boom")
    status = runtime.status()
    assert set(status["words"]["verbs"]) == {"start", "stop", "restart"}
    assert status["operation"]["label"]["en"] == "Failed"
    assert status["operation"]["label"]["pl"] == "Nie udało się"
    assert status["dia"]["actions"] == runtime.allowed_verbs(
        status["dia"]["load"], status["dia"]["active"]
    )
    for words in (*runtime.VERB_LABELS.values(), *runtime.RESULT_LABELS.values()):
        assert set(words) == LANGUAGES


def test_surfaces_use_the_allowed_verbs():
    from pathlib import Path

    ui = Path(runtime.__file__).parents[1] / "ui"
    assert "actions?.includes" in (ui / "static/js/views/settings_devices.js").read_text()
    assert "canService" in (ui / "plasmoid/contents/ui/StatusHeader.qml").read_text()


def test_state_words_fall_back_to_english_for_other_languages():
    assert runtime.state_label("loaded", "active", "de") == "Läuft"
    assert runtime.state_label("loaded", "failed", "cs") == "Error"  # not "Unknown"
