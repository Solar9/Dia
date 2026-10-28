import asyncio
import base64
import io
import re
import wave
from pathlib import Path

import pytest

aiohttp = pytest.importorskip("aiohttp")
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

from dia.channels.api import ApiChannel  # noqa: E402
from dia.config import parse_config  # noqa: E402
from dia.orchestrator import Orchestrator  # noqa: E402
from dia.voice import SpeechToText, TextToSpeech  # noqa: E402
from dia.voice.talk import Talk, audio_type  # noqa: E402


@pytest.fixture
async def client(tmp_path: Path, repo: Path):
    (tmp_path / "dia.toml").write_text("[dia]\n")
    config = parse_config(
        {
            "dia": {
                "data_dir": str(tmp_path / "data"),
                "default_agent": "fake",
                "language": "pl",
                "brain": ["rules"],
            },
            "agents": {
                "fake": {
                    "type": "command",
                    "argv": ["sh", "-c", 'echo x > x.txt; echo "did: $0"', "{prompt}"],
                }
            },
            "projects": {"demo": {"path": str(repo)}},
            "pipelines": {
                "two": {
                    "steps": [{"agent": "fake", "prompt": "a"}, {"agent": "fake", "prompt": "b"}]
                }
            },
        },
        tmp_path / "dia.toml",
    )
    api = ApiChannel("ui", {"port": 0}, Orchestrator(config))
    server = TestServer(api.app(), host="127.0.0.1")
    async with TestClient(server) as c:
        api.local_hosts.add(f"127.0.0.1:{server.port}")
        api.allowed_hosts.add(f"127.0.0.1:{server.port}")
        api.dia.store.listeners.append(api._on_task_saved)
        api.dia.listeners.append(api._on_event)
        c.api = api
        c.auth = {"Authorization": f"Bearer {api.token}"}
        yield c


async def wait_status(c, task_id: str, status: str) -> dict:
    for _ in range(100):
        task = await (await c.get(f"/api/tasks/{task_id}", headers=c.auth)).json()
        if task["status"] == status:
            return task
        await asyncio.sleep(0.05)
    raise AssertionError(f"task never reached {status}: {task['status']}")


async def test_token_and_host_are_required(client) -> None:
    assert (await client.get("/api/status")).status == 401
    assert (await client.get("/api/status", headers={"Authorization": "Bearer nope"})).status == 401
    evil = {**client.auth, "Host": "attacker.example:8765"}
    assert (await client.get("/api/status", headers=evil)).status == 403
    page = await client.get("/")  # the page itself holds no data
    assert page.status == 200 and "importmap" in await page.text()
    token_file = client.api.dia.config.data_dir / "api-token"
    assert token_file.stat().st_mode & 0o777 == 0o600


async def test_run_task_review_and_merge(client, repo: Path) -> None:
    status = await (await client.get("/api/status", headers=client.auth)).json()
    assert [a["name"] for a in status["agents"]] == ["fake"] and status["language"] == "pl"

    created = await client.post(
        "/api/tasks", headers=client.auth, json={"project": "demo", "prompt": "add x"}
    )
    assert created.status == 201
    task = await wait_status(client, (await created.json())["id"], "done")
    assert task["summary"].startswith("did: add x")

    diff = await (await client.get(f"/api/tasks/{task['id']}/diff", headers=client.auth)).text()
    assert "+x" in diff
    listed = await (await client.get("/api/tasks", headers=client.auth)).json()
    assert listed[0]["diffstat"] == {"files": 1, "added": 1, "removed": 0}
    merged = await client.post(f"/api/tasks/{task['id']}/merge", headers=client.auth)
    assert (await merged.json())["message"].startswith("merged as")
    assert (repo / "x.txt").exists()

    bad = await client.post(f"/api/tasks/{task['id']}/merge", headers=client.auth)
    assert bad.status == 400 and "already merged" in (await bad.json())["error"]
    unknown = await client.post(
        "/api/tasks", headers=client.auth, json={"project": "nope", "prompt": "x"}
    )
    assert unknown.status == 400


async def test_plans_and_live_updates(client) -> None:
    ws = await client.ws_connect(f"/ws?token={client.api.token}")
    plan = await (
        await client.post(
            "/api/plans",
            headers=client.auth,
            json={"project": "demo", "goal": "g", "pipeline": "two"},
        )
    ).json()
    assert plan["status"] == "planned"
    run = await client.post(f"/api/tasks/{plan['id']}/run-plan", headers=client.auth)
    assert run.status == 202
    statuses = []
    while "done" not in statuses:
        message = await asyncio.wait_for(ws.receive_json(), 5)
        if message["type"] == "task" and message["task"]["id"] == plan["id"]:
            statuses.append(message["task"]["status"])
    assert statuses[0] in ("planned", "queued") and statuses[-1] == "done"
    await ws.close()


async def test_chat_uses_the_brain(client) -> None:
    answer = await (
        await client.post("/api/chat", headers=client.auth, json={"text": "Dziastatus"})
    ).json()
    assert answer["action"] == "status" and answer["reply"].startswith("Gotowi agenci: fake.")


async def test_config_is_validated_before_saving(client) -> None:
    path = client.api.dia.config.source
    bad = await client.put("/api/config", headers=client.auth, json={"text": "[projects.x]\n"})
    assert bad.status == 400 and "needs a 'path'" in (await bad.json())["error"]
    assert path.read_text() == "[dia]\n"
    good = await client.put(
        "/api/config", headers=client.auth, json={"text": '[dia]\nlanguage = "en"\n'}
    )
    assert (await good.json())["restart_required"] is True
    assert "language" in path.read_text() and path.with_suffix(".toml.bak").read_text() == "[dia]\n"


async def test_themes(client, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    mine = tmp_path / "cfg" / "dia" / "themes"
    mine.mkdir(parents=True)
    (mine / "solar.css").write_text(":root { --accent: orange; }")
    themes = await (await client.get("/api/themes", headers=client.auth)).json()
    assert themes["built_in"] == ["dark", "light", "midnight"] and themes["custom"] == ["solar"]
    css = await client.get("/themes/solar.css")
    assert css.status == 200 and "orange" in await css.text()
    assert (await client.get("/themes/..%2Fapi-token.css")).status == 404


async def test_voice_without_voice_channel(client) -> None:
    response = await client.post("/api/voice/toggle", headers=client.auth)
    assert response.status == 409 and "not configured" in (await response.json())["error"]


async def test_paired_device_from_another_host(client) -> None:
    api = client.api
    api.remote = True
    api.allowed_hosts.add("dia.example.ts.net")
    api.options["public_url"] = "https://dia.example.ts.net"
    phone = {"Host": "dia.example.ts.net"}

    # The owner token works only on this computer, not through another host name.
    owner_remote = {**phone, **client.auth}
    assert (await client.get("/api/status", headers=owner_remote)).status == 401

    paired = await (
        await client.post("/api/devices", json={"name": "phone"}, headers=client.auth)
    ).json()
    assert paired["url"] == f"https://dia.example.ts.net/#token={paired['token']}"
    device = {**phone, "Authorization": f"Bearer {paired['token']}"}

    status = await (await client.get("/api/status", headers=device)).json()
    assert status["device"] == "phone"
    assert (await client.get("/api/tasks", headers=device)).status == 200
    # ...but no configuration, microphone or device management.
    for path in ("/api/config", "/api/devices"):
        assert (await client.get(path, headers=device)).status == 403
    assert (await client.post("/api/voice/toggle", headers=device)).status == 403

    listed = await (await client.get("/api/devices", headers=client.auth)).json()
    assert [d["name"] for d in listed["devices"]] == ["phone"]
    assert "token_hash" not in listed["devices"][0]
    device_id = listed["devices"][0]["id"]

    # Full access, given at the computer: settings and tools, never secrets or pairing.
    assert (
        await client.patch(f"/api/devices/{device_id}", json={"full": True}, headers=device)
    ).status == 403
    full = await client.patch(f"/api/devices/{device_id}", json={"full": True}, headers=client.auth)
    assert (await full.json())["full"] is True
    assert (await (await client.get("/api/status", headers=device)).json())["device_full"] is True
    for path in ("/api/config", "/api/settings"):
        assert (await client.get(path, headers=device)).status == 200
    for path in ("/api/devices", "/api/secrets"):
        assert (await client.get(path, headers=device)).status == 403
    await client.patch(f"/api/devices/{device_id}", json={"full": False}, headers=client.auth)
    assert (await client.get("/api/settings", headers=device)).status == 403
    assert (await client.delete(f"/api/devices/{device_id}", headers=client.auth)).status == 200
    assert (await client.get("/api/tasks", headers=device)).status == 401


async def test_pwa_files(client) -> None:
    manifest = await (await client.get("/manifest.webmanifest")).json()
    assert manifest["display"] == "standalone"
    for icon in manifest["icons"]:
        assert (await client.get(icon["src"])).status == 200
    assert (await client.get("/sw.js")).status == 200


async def test_settings_forms_secrets_and_schedules(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    auth = client.auth
    meta = await (await client.get("/api/settings", headers=auth)).json()
    assert "butler" in meta["personalities"] and "weather" in meta["skills"]

    changes = {"assistant": {"user_name": "Dawid", "personality": "butler"}, "ui": {"port": 9}}
    saved = await (
        await client.put("/api/settings", json={"changes": changes}, headers=auth)
    ).json()
    assert saved["restart_required"] == ["ui"]
    assert client.api.dia.config.assistant["user_name"] == "Dawid"  # applied at once
    bad = await client.put("/api/settings", json={"changes": {"projects": {"x": {}}}}, headers=auth)
    assert bad.status == 400  # invalid result: nothing saved

    put = await client.put("/api/secrets/ELEVENLABS_API_KEY", json={"value": "sk-1"}, headers=auth)
    assert put.status == 200
    listed = await (await client.get("/api/secrets", headers=auth)).json()
    assert {"name": "ELEVENLABS_API_KEY", "label": "ElevenLabs (voice)", "set": True} in listed
    assert "sk-1" not in str(listed)

    job = await (
        await client.post(
            "/api/schedules", json={"cron": "0 7 * * *", "text": "status"}, headers=auth
        )
    ).json()
    jobs = await (await client.get("/api/schedules", headers=auth)).json()
    assert jobs[0]["id"] == job["id"] and jobs[0]["next"]
    paused = await client.patch(
        f"/api/schedules/{job['id']}", json={"enabled": False}, headers=auth
    )
    assert (await paused.json())["enabled"] is False
    assert (await client.delete(f"/api/schedules/{job['id']}", headers=auth)).status == 200
    bad_cron = await client.post("/api/schedules", json={"cron": "7am", "text": "x"}, headers=auth)
    assert bad_cron.status == 400
    usage = await (await client.get("/api/usage?days=7", headers=auth)).json()
    assert usage["days"] == 7 and "limits" in usage


async def test_preferences_and_camera(client) -> None:
    auth = client.auth
    added = await client.post("/api/preferences", headers=auth, json={"text": "krótko, bez emoji"})
    assert (await added.json())["text"] == "krótko, bez emoji"
    prefs = await (await client.get("/api/preferences", headers=auth)).json()
    assert [p["text"] for p in prefs["accepted"]] == ["krótko, bez emoji"]
    removed = await client.post("/api/preferences/0/remove", headers=auth)
    assert (await removed.json())["accepted"] == []
    assert (await client.post("/api/preferences/5/accept", headers=auth)).status == 404

    status = await (await client.get("/api/status", headers=auth)).json()
    assert status["camera"] is False
    on = await client.post("/api/camera", headers=auth, json={"on": True})
    assert (await on.json()) == {"camera": True} and client.api.dia.camera_enabled
    await client.post("/api/camera", headers=auth, json={"on": False})
    assert not client.api.dia.camera_enabled


async def test_scorecard_and_experiments(client) -> None:
    rows = await (await client.get("/api/scorecard?weeks=3", headers=client.auth)).json()
    assert len(rows) == 3 and rows[-1]["tasks"] == 0
    usage = await (await client.get("/api/usage", headers=client.auth)).json()
    assert len(usage["scorecard"]) == 8
    # one agent and no approaches: nothing to compare, refused before anything runs
    bad = await client.post(
        "/api/experiments", json={"project": "demo", "question": "faster?"}, headers=client.auth
    )
    assert bad.status == 400 and "two variants" in (await bad.json())["error"]
    started = await client.post(
        "/api/experiments",
        json={"project": "demo", "question": "faster?", "approaches": ["a", "b"]},
        headers=client.auth,
    )
    assert started.status == 202
    task = await wait_status(client, (await started.json())["id"], "done")
    assert task["mode"] == "experiment" and "Recommended: variant" in task["summary"]


async def test_decisions_why_profile_and_impact(client, repo: Path) -> None:
    started = await client.post(
        "/api/tasks", json={"project": "demo", "prompt": "add the inventory"}, headers=client.auth
    )
    task = await wait_status(client, (await started.json())["id"], "done")
    r = await client.post(
        f"/api/tasks/{task['id']}/discard", json={"reason": "not now"}, headers=client.auth
    )
    assert r.status == 200
    [decision] = await (await client.get("/api/decisions", headers=client.auth)).json()
    assert (decision["kind"], decision["reason"]) == ("discard", "not now")
    found = await (await client.get("/api/why?q=inventory", headers=client.auth)).json()
    assert "why: not now" in found["text"]
    await client.put("/api/profile", json={"text": "## Accepts\n- tests"}, headers=client.auth)
    saved = await (await client.get("/api/profile", headers=client.auth)).json()
    assert "- tests" in saved["text"]
    url = "/api/projects/demo/impact?q=teleport"
    impact = await (await client.get(url, headers=client.auth)).json()
    assert impact["targets"] == [] and "Nothing in the project matches" in impact["text"]


async def test_debt_and_debug_endpoints(client, repo: Path) -> None:
    debt = await (await client.get("/api/projects/demo/debt", headers=client.auth)).json()
    assert debt["items"] == [] and "No technical debt" in debt["text"]
    r = await client.post("/api/projects/demo/debt/1/fix", headers=client.auth)
    assert r.status == 400
    started = await client.post(
        "/api/debug", json={"project": "demo", "bug": "it crashes"}, headers=client.auth
    )
    assert started.status == 202
    task = await wait_status(client, (await started.json())["id"], "done")
    assert task["mode"] == "debug" and "No hypothesis was confirmed" in task["summary"]


async def test_goals_work_suggestions_health(client) -> None:
    assert await (await client.get("/api/goals", headers=client.auth)).json() == []
    work = await (await client.get("/api/work", headers=client.auth)).json()
    assert "demo" in work["profiles"] and work["current"] is None
    started = await client.post("/api/work/start", json={"name": "demo"}, headers=client.auth)
    assert (await started.json())["text"].startswith("Work on demo")
    assert await (await client.get("/api/suggestions", headers=client.auth)).json() == []
    assert await (await client.get("/api/health", headers=client.auth)).json() == {}


async def test_chat_sessions(client) -> None:
    h = client.auth
    main = await (await client.get("/api/sessions", headers=h)).json()
    assert [s["id"] for s in main] == ["owner"] and main[0]["main"]
    a = (await (await client.post("/api/sessions", json={}, headers=h)).json())["id"]
    b = (await (await client.post("/api/sessions", json={"title": "Steam"}, headers=h)).json())[
        "id"
    ]
    await client.post("/api/chat", json={"text": "status", "session": a}, headers=h)
    await client.post("/api/chat", json={"text": "jaka pogoda?", "session": b}, headers=h)
    first = (await (await client.get(f"/api/sessions/{a}", headers=h)).json())["messages"]
    assert [m["from"] for m in first] == ["me", "dia"] and first[0]["text"] == "status"
    listed = {s["id"]: s for s in await (await client.get("/api/sessions", headers=h)).json()}
    assert listed[a]["title"] == "status" and listed[b]["title"] == "Steam"
    assert listed["owner"]["messages"] == 0  # the other sessions did not touch the main one
    await client.patch(f"/api/sessions/{a}", json={"title": "Nova"}, headers=h)
    await client.delete(f"/api/sessions/{b}", headers=h)
    listed = {s["id"]: s for s in await (await client.get("/api/sessions", headers=h)).json()}
    assert listed[a]["title"] == "Nova" and b not in listed
    bad = await client.post("/api/chat", json={"text": "x", "session": "chat-nope"}, headers=h)
    assert bad.status == 400


async def test_status_has_the_version(client) -> None:
    from dia import __version__

    status = await (await client.get("/api/status", headers=client.auth)).json()
    assert status["version"] == __version__
    manifest = await (await client.get("/manifest.webmanifest")).json()
    assert {i["purpose"] for i in manifest["icons"] if "purpose" in i} == {"any", "maskable"}


async def test_a_session_can_talk_straight_to_a_model(client) -> None:
    h = client.auth
    providers = await (await client.get("/api/chat/providers", headers=h)).json()
    assert providers[0]["id"] == "dia"
    sid = (await (await client.post("/api/sessions", json={}, headers=h)).json())["id"]
    await client.patch(f"/api/sessions/{sid}", json={"provider": "agent:fake"}, headers=h)
    answer = await (
        await client.post("/api/chat", json={"text": "hej", "session": sid}, headers=h)
    ).json()
    assert answer["provider"] == "agent:fake" and answer["reply"].endswith("hej")
    messages = (await (await client.get(f"/api/sessions/{sid}", headers=h)).json())["messages"]
    assert [m["from"] for m in messages] == ["me", "dia"] and messages[1][
        "model"
    ] == "agent:fake:default"
    tasks = await (await client.get("/api/tasks", headers=h)).json()
    assert tasks == []  # plain chat runs no task
    main = await client.patch("/api/sessions/owner", json={"provider": "agent:fake"}, headers=h)
    assert main.status == 400  # the main conversation stays Dia's


async def test_skills_tools_and_desktop_from_the_app(client, monkeypatch) -> None:
    from dia.skills import NeedsConfirmation, builtin

    async def fake_json(url, params=None, timeout=15):
        return {"bitcoin": {"usd": 100.0, "usd_24h_change": -1.0}}

    monkeypatch.setattr(builtin, "fetch_json", fake_json)
    skills = await (await client.get("/api/skills", headers=client.auth)).json()
    assert "coins" in next(s for s in skills if s["name"] == "crypto")["args"]
    answer = await client.post(
        "/api/skills/crypto", json={"args": {"coins": "btc"}}, headers=client.auth
    )
    assert "BTC: 100.00 USD" in (await answer.json())["text"]
    assert (await client.post("/api/skills/nope", json={}, headers=client.auth)).status == 404

    done = []

    async def lock(self, args):
        async def action():
            done.append(True)
            return "locked"

        raise NeedsConfirmation("Lock the door?", action)

    monkeypatch.setattr(builtin.CryptoSkill, "run", lock)
    asked = await (await client.post("/api/skills/crypto", json={}, headers=client.auth)).json()
    assert asked == {"question": "Lock the door?"} and not done
    yes = await client.post("/api/skills/crypto", json={"confirm": True}, headers=client.auth)
    assert (await yes.json())["text"] == "locked" and done

    # Dia's CLI commands with their output; only the listed ones.
    tool = await client.post("/api/tools", json={"command": "limits"}, headers=client.auth)
    assert tool.status == 200 and "fake" in (await tool.json())["output"]
    bad = await client.post("/api/tools", json={"command": "serve"}, headers=client.auth)
    assert bad.status == 404
    wrong = await client.post("/api/tools", json={"command": "check"}, headers=client.auth)
    assert wrong.status == 400 and "required" in (await wrong.json())["output"]

    state = await (await client.get("/api/desktop", headers=client.auth)).json()
    assert set(state["shortcuts"]) == {"menu", "desktop", "autostart"}


async def test_runtime_controls_require_confirmation_and_validate_policy(client, monkeypatch):
    from dia import runtime

    calls = []
    monkeypatch.setattr(runtime, "enqueue", lambda *args: calls.append(args))
    denied = await client.post(
        "/api/desktop/runtime", headers=client.auth, json={"component": "dia", "verb": "stop"}
    )
    assert denied.status == 400 and not calls
    accepted = await client.post(
        "/api/desktop/runtime",
        headers=client.auth,
        json={"component": "dia", "verb": "stop", "confirmed": True},
    )
    assert accepted.status == 200 and calls[0][:2] == ("dia", "stop")
    invalid = await client.post(
        "/api/desktop/startup",
        headers=client.auth,
        json={"autostart": "false", "ollama": "manual", "warmup": True},
    )
    assert invalid.status == 400


async def test_a_terminal_session_can_be_taken_over_and_continued(client, tmp_path, monkeypatch):
    from dia import sessions

    h = client.auth
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    folder = re.sub(r"[^A-Za-z0-9]", "-", str(tmp_path))
    transcript = tmp_path / ".claude" / "projects" / folder / "sid1.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text('{"type":"user","message":{"role":"user","content":"hej"}}\n')
    live = sessions.CliSession(7, "claude-code", tmp_path, 5.0, None, None, False)
    ended = []
    monkeypatch.setattr(sessions, "find_sessions", lambda: [live])
    monkeypatch.setattr(sessions, "end_process", lambda pid: ended.append(pid) or True)
    script = tmp_path / "claude"
    script.write_text('#!/bin/sh\necho \'{"result":"done","session_id":"sid1"}\'\n')
    script.chmod(0o755)
    client.api.dia.config.agents["cc"] = {"type": "claude-code", "command": str(script)}
    client.api.dia.config.raw["sandbox"] = {"enabled": False}  # the stub lives outside any sandbox

    item = await (await client.post("/api/cli-sessions/7/capture", headers=h)).json()
    assert ended == [7] and item["id"] == "sid1" and item["resume"] == "claude --resume sid1"
    assert [c["id"] for c in await (await client.get("/api/cli-captured", headers=h)).json()] == [
        "sid1"
    ]
    talk = await (await client.get("/api/cli-captured/sid1/transcript", headers=h)).json()
    assert talk["messages"][0]["text"] == "hej"
    sent = await client.post("/api/cli-captured/sid1/send", json={"text": "go on"}, headers=h)
    answer = await sent.json()
    assert answer.get("reply") == "done", answer
    released = await (await client.delete("/api/cli-captured/sid1", headers=h)).json()
    assert released["resume"] == "claude --resume sid1"
    assert await (await client.get("/api/cli-captured", headers=h)).json() == []


# ------------------------------------------------- a phone's own voice ---
# /api/talk: the phone's recording in, Dia's answer and her speech out.


class HeardSTT(SpeechToText):
    kind = "fake"

    def __init__(self, text: str, problem: str | None = None) -> None:
        super().__init__()
        self.text, self.problem, self.heard = text, problem, []

    def check(self) -> str | None:
        return self.problem

    async def transcribe(self, audio: Path, language: str | None = None) -> str:
        self.heard.append((audio.read_bytes()[:4], language))
        return self.text


class WavTTS(TextToSpeech):
    kind = "fake"

    def __init__(self) -> None:
        super().__init__()
        self.said: list[str] = []

    async def synthesize(self, text: str, output: Path) -> None:
        self.said.append(text)
        output.write_bytes(b"RIFF....WAVEfake")


def recording(seconds: float = 0.5) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\0\0" * int(16000 * seconds))
    return buffer.getvalue()


def engines(api, text: str = "Dziastatus", problem: str | None = None) -> tuple:
    talk = Talk({}, "pl")
    talk._stt, talk._tts = HeardSTT(text, problem), WavTTS()
    api._talk_engines = talk
    return talk._stt, talk._tts


async def test_phone_talks_through_dias_own_speech(client) -> None:
    stt, tts = engines(client.api)
    response = await client.post("/api/talk", data=recording(), headers=client.auth)
    answer = await response.json()
    assert stt.heard == [(b"RIFF", "pl")]
    assert answer["heard"] == "Dziastatus" and answer["action"] == "status"
    assert answer["reply"].startswith("Gotowi agenci: fake.")
    assert tts.said and tts.said[0].startswith("Gotowi agenci")
    assert base64.b64decode(answer["audio"]).startswith(b"RIFF")
    assert answer["audio_type"] == "audio/wav"
    status = await (await client.get("/api/status", headers=client.auth)).json()
    assert status["talk"] is True


async def test_quiet_mode_answers_in_text_only(client) -> None:
    _, tts = engines(client.api)
    client.api.dia.set_quiet(True)
    answer = await (await client.post("/api/talk", data=recording(), headers=client.auth)).json()
    assert answer["reply"] and "audio" not in answer and tts.said == []


async def test_nothing_heard_and_bad_input(client) -> None:
    engines(client.api, text="")
    answer = await (await client.post("/api/talk", data=recording(), headers=client.auth)).json()
    assert answer == {"heard": ""}
    bad = await client.post("/api/talk", data=b"not audio", headers=client.auth)
    assert bad.status == 400
    big = await client.post("/api/talk", data=recording(31), headers=client.auth)
    assert big.status == 413


async def test_without_speech_recognition_the_phone_is_told_why(client) -> None:
    engines(client.api, problem="faster-whisper is not installed")
    response = await client.post("/api/talk", data=recording(), headers=client.auth)
    assert response.status == 409 and "faster-whisper" in (await response.json())["error"]
    status = await (await client.get("/api/status", headers=client.auth)).json()
    assert status["talk"] is False


async def test_a_paired_phone_may_talk_but_not_use_the_computers_microphone(client) -> None:
    engines(client.api)
    api = client.api
    api.remote = True
    api.allowed_hosts.add("dia.example.ts.net")
    paired = await (
        await client.post("/api/devices", json={"name": "phone"}, headers=client.auth)
    ).json()
    phone = {"Host": "dia.example.ts.net", "Authorization": f"Bearer {paired['token']}"}
    assert (await client.post("/api/voice/toggle", headers=phone)).status == 403
    answer = await (await client.post("/api/talk", data=recording(), headers=phone)).json()
    assert answer["heard"] == "Dziastatus" and answer["reply"]


def test_audio_type() -> None:
    assert audio_type(b"RIFF....WAVE") == "audio/wav"
    assert audio_type(b"ID3\x04") == "audio/mpeg"
    assert audio_type(b"OggS") == "audio/ogg"


def test_talk_uses_the_voice_channels_engines_and_language() -> None:
    class Config:
        language = "en"
        channels = {"voice": {"type": "voice", "language": "pl", "stt": {"type": "command"}}}

    talk = Talk.from_config(Config())
    assert talk.language == "pl" and talk.options["stt"] == {"type": "command"}
    assert "argv" in (talk.check() or "")


async def test_themes_of_the_app_the_phone_and_the_widget(client) -> None:
    h = client.auth
    first = await (await client.get("/api/theme", headers=h)).json()
    assert first == {**first, "name": "dark", "phone": None, "widget": None, "effective": "dark"}
    assert first["colors"]["accent"] == "#b4a2ff"

    # The app's theme: every open page switches at once; phone and widget follow it.
    ws = await client.ws_connect(f"/ws?token={client.api.token}")
    saved = await client.put("/api/theme", json={"name": "midnight"}, headers=h)
    assert (await saved.json())["colors"]["accent"] == "#22d3ee"
    message = await ws.receive_json(timeout=2)
    assert message == {"type": "theme", "name": "midnight", "phone": None, "widget": None}
    await ws.close()
    status = await (await client.get("/api/status", headers=h)).json()
    assert status["theme"] == "midnight" and status["theme_colors"]["bg"] == "#070b14"
    assert status["widget_theme_colors"]["accent"] == "#22d3ee"
    # see-through colours as Qt reads them (#AARRGGBB) for the KDE widget
    assert status["theme_colors"]["accent-soft"] == "#1f22d3ee"

    # The widget's own theme; then the same as the app's again.
    await client.put("/api/theme", json={"widget": "light"}, headers=h)
    status = await (await client.get("/api/status", headers=h)).json()
    assert status["theme"] == "midnight" and status["widget_theme_colors"]["bg"] == "#fbfbfc"
    await client.put("/api/theme", json={"widget": None}, headers=h)
    status = await (await client.get("/api/status", headers=h)).json()
    assert status["widget_theme_colors"]["bg"] == "#070b14"

    for bad in ({"name": "nope"}, {"name": "../api-token"}, {"name": None}, {"colour": "dark"}):
        assert (await client.put("/api/theme", json=bad, headers=h)).status == 400

    # A paired phone: its own theme, or the app's; it may set only its own.
    api = client.api
    api.remote = True
    api.allowed_hosts.add("dia.example.ts.net")
    paired = await (await client.post("/api/devices", json={"name": "phone"}, headers=h)).json()
    phone = {"Host": "dia.example.ts.net", "Authorization": f"Bearer {paired['token']}"}
    assert (await (await client.get("/api/status", headers=phone)).json())["theme"] == "midnight"
    assert (await client.put("/api/theme", json={"name": "light"}, headers=phone)).status == 403
    own = await (await client.put("/api/theme", json={"phone": "light"}, headers=phone)).json()
    assert own["effective"] == "light" and own["name"] == "midnight"
    assert (await (await client.get("/api/status", headers=phone)).json())["theme"] == "light"
    assert (await (await client.get("/api/status", headers=h)).json())["theme"] == "midnight"


async def test_new_cli_session_with_a_chosen_agent_and_model(client, tmp_path: Path) -> None:
    script = tmp_path / "claude"
    script.write_text(
        '#!/bin/sh\nprintf \'{"result": "ready", "session_id": "s-123"}\'\necho "$*" > "$0.args"\n'
    )
    script.chmod(0o755)
    client.api.dia.config.agents["cc"] = {"type": "claude-code", "command": str(script)}
    h = client.auth
    body = {"agent": "cc", "model": "opus", "project": "demo", "text": "hello"}
    made = await client.post("/api/cli-captured", json=body, headers=h)
    item = await made.json()
    assert made.status == 201 and item["id"] == "s-123" and item["reply"] == "ready"
    assert item["kind"] == "claude-code" and item["model"] == "opus" and item["started_in_app"]
    assert item["resume"] == "claude --resume s-123"
    assert "--model opus" in (tmp_path / "claude.args").read_text()
    listed = await (await client.get("/api/cli-captured", headers=h)).json()
    assert [c["id"] for c in listed] == ["s-123"]
    # an agent whose conversation can't go on, an unknown project, nothing to say
    for bad in ({**body, "agent": "fake"}, {**body, "project": "nope"}, {**body, "text": " "}):
        assert (await client.post("/api/cli-captured", json=bad, headers=h)).status == 400
