import pytest

from dia import desktop, runtime, service


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
