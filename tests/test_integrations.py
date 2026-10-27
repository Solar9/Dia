from datetime import date, timedelta
from pathlib import Path

import pytest

from dia.assistant import Assistant
from dia.brains import Intent
from dia.config import parse_config
from dia.orchestrator import Orchestrator
from dia.skills import integrations

ICS = """BEGIN:VCALENDAR
BEGIN:VEVENT
SUMMARY:Stand-up
DTSTART;TZID=Europe/Warsaw:20261019T093000
DTEND;TZID=Europe/Warsaw:20261019T094500
RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR
END:VEVENT
BEGIN:VEVENT
SUMMARY:Dentysta\\, kontrola
LOCATION:Kraków
DTSTART:20261023T120000Z
END:VEVENT
BEGIN:VEVENT
SUMMARY:Urodziny Ani
DTSTART;VALUE=DATE:20200314
RRULE:FREQ=YEARLY
END:VEVENT
END:VCALENDAR
"""


def test_ics_and_recurrence() -> None:
    events = integrations.parse_ics(ICS)
    standup, dentist, birthday = events
    assert dentist["summary"] == "Dentysta, kontrola" and dentist["location"] == "Kraków"
    assert integrations.occurs_on(standup, date(2026, 10, 21)) is not None  # Wednesday
    assert integrations.occurs_on(standup, date(2026, 10, 22)) is None  # Thursday
    assert integrations.occurs_on(birthday, date(2027, 3, 14)) == date(2027, 3, 14)
    assert integrations.occurs_on(dentist, date(2026, 10, 23)) is not None


def make(tmp_path: Path, **sections) -> Orchestrator:
    raw = {"dia": {"data_dir": str(tmp_path / "d"), "language": "pl"}, **sections}
    return Orchestrator(parse_config(raw), use_memory=False)


async def test_calendar_skill(tmp_path: Path, monkeypatch) -> None:
    today = date.today()
    ics = (
        "BEGIN:VEVENT\nSUMMARY:Playtest Nova\n"
        f"DTSTART:{today:%Y%m%d}T150000\nEND:VEVENT\n"
        "BEGIN:VEVENT\nSUMMARY:Jutro rano\n"
        f"DTSTART;VALUE=DATE:{today + timedelta(days=1):%Y%m%d}\nEND:VEVENT\n"
    )

    async def fake_fetch(url, params=None, timeout=15):
        return ics.encode()

    monkeypatch.setattr(integrations, "fetch", fake_fetch)
    monkeypatch.setenv("DIA_CALENDAR_URL", "https://calendar.example/private.ics")
    assistant = Assistant(make(tmp_path), brains=[])
    assert await assistant.run_skill("calendar") == "Dziś:\n- 15:00 Playtest Nova"
    tomorrow = await assistant.run_skill("calendar", {"day": "tomorrow"})
    assert tomorrow == "Jutro:\n- cały dzień Jutro rano"

    async def unreachable(url, params=None, timeout=15):
        raise ConnectionRefusedError("connection refused")

    monkeypatch.setattr(integrations, "fetch", unreachable)
    answer = await assistant.run_skill("calendar")
    assert "Nie mogę" in answer and "nic w kalendarzu" not in answer

    monkeypatch.delenv("DIA_CALENDAR_URL")
    assert "DIA_CALENDAR_URL" in await assistant.run_skill("calendar")


class FakeIMAP:
    def __init__(self, host, port):
        assert (host, port) == ("imap.example", 993)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def login(self, user, password):
        assert password == "app-password"

    def select(self, folder, readonly=False):
        assert readonly  # never marks anything as read

    def search(self, charset, criterion):
        return "OK", [b"1 2"]

    def fetch(self, msg_id, parts):
        assert "PEEK" in parts
        header = b"From: Ann <ann@example.com>\r\nSubject: =?utf-8?q?Raport_z_test=C3=B3w?=\r\n\r\n"
        return "OK", [(b"1", header)]


async def test_mail_skill_reads_without_marking(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(integrations.imaplib, "IMAP4_SSL", FakeIMAP)
    monkeypatch.setenv("DIA_MAIL_PASSWORD", "app-password")
    dia = make(tmp_path, skills={"mail": {"host": "imap.example", "user": "me"}})
    text = await Assistant(dia, brains=[]).run_skill("mail")
    assert text.startswith("Nieprzeczytane: 2") and "Ann: Raport z testów" in text


STATES = [
    {"entity_id": "light.biurko", "state": "off", "attributes": {"friendly_name": "Biurko"}},
    {
        "entity_id": "lock.front_door",
        "state": "locked",
        "attributes": {"friendly_name": "Drzwi wejściowe"},
    },
    {
        "entity_id": "scene.tryb_pracy",
        "state": "scening",
        "attributes": {"friendly_name": "Tryb pracy"},
    },
]


@pytest.fixture
def home(tmp_path: Path, monkeypatch):
    calls = []

    def fake_request(self, path, body=None):
        if path == "/api/states":
            return STATES
        calls.append((path, body))
        return []

    monkeypatch.setattr(integrations.HomeSkill, "_request", fake_request)
    dia = make(tmp_path, skills={"home": {"url": "http://ha.local:8123"}})
    return Assistant(dia, brains=[]), calls


async def test_home_lights_and_scenes(home) -> None:
    assistant, calls = home
    done = await assistant.run_skill("home", {"action": "on", "target": "biurko"})
    assert done.startswith("Zrobione: Biurko") and calls[-1] == (
        "/api/services/light/turn_on",
        {"entity_id": "light.biurko"},
    )
    await assistant.run_skill("home", {"action": "on", "target": "tryb pracy"})
    assert calls[-1][0] == "/api/services/scene/turn_on"
    assert "Nie znam" in await assistant.run_skill("home", {"action": "on", "target": "sauna"})


async def test_unlocking_asks_first(home) -> None:
    assistant, calls = home
    question = await assistant.run_skill("home", {"action": "unlock", "target": "drzwi wejściowe"})
    assert question.endswith("Powiedz tak albo nie.") and calls == []
    answer = await assistant.execute(Intent("confirm"))
    assert answer.text.startswith("Zrobione") and calls == [
        ("/api/services/lock/unlock", {"entity_id": "lock.front_door"})
    ]


async def test_itch_publish_only_finished_builds(tmp_path: Path, monkeypatch) -> None:
    from dia.orchestrator import TaskActionError
    from dia.release import Releases
    from dia.store import TaskRecord

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "butler.log"
    (bin_dir / "butler").write_text(f'#!/bin/sh\necho "$@" >> {log}\n')
    (bin_dir / "butler").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")
    out = tmp_path / "builds" / "Linux"
    out.mkdir(parents=True)
    (out / "nova.x86_64").write_text("bin")
    repo = tmp_path / "repo"
    repo.mkdir()
    dia = make(tmp_path, builds={"itch": "solar/nova"}, projects={"nova": {"path": str(repo)}})
    task = TaskRecord(
        id="b1",
        project="nova",
        agent="-",
        mode="build",
        prompt="build",
        status="done",
        details={
            "version": "0.2",
            "builds": [{"preset": "Linux", "files": [str(out / "nova.x86_64")]}],
        },
    )
    dia.store.save(task)
    assert await Releases(dia).publish_itch("b1") == ["solar/nova:linux"]
    assert log.read_text().split() == ["push", str(out), "solar/nova:linux", "--userversion", "0.2"]
    assert dia.store.audit(action="build.publish")
    task.status = "failed"
    dia.store.save(task)
    with pytest.raises(TaskActionError):
        await Releases(dia).publish_itch("b1")


async def test_notion_skill(tmp_path: Path, monkeypatch) -> None:
    calls = []
    page = {
        "id": "p1",
        "object": "page",
        "properties": {"title": {"type": "title", "title": [{"plain_text": "Pomysły na Nova"}]}},
    }

    def fake_request(self, method, path, body=None):
        calls.append((method, path, body))
        if path == "/search":
            return {"results": [page] if body["query"] != "nic" else []}
        if path.startswith("/blocks/p1/children"):
            return {
                "results": [
                    {"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "Parry"}]}},
                    {
                        "type": "to_do",
                        "to_do": {"rich_text": [{"plain_text": "Co-op na 4 graczy"}]},
                    },
                ]
            }
        if path == "/pages":
            return {"id": "new"}
        raise AssertionError(path)

    monkeypatch.setattr(integrations.NotionSkill, "_request", fake_request)
    dia = make(tmp_path, skills={"notion": {"parent": "abc-123"}})
    assistant = Assistant(dia, brains=[])
    assert "NOTION_TOKEN" in await assistant.run_skill("notion", {"query": "nova"})

    monkeypatch.setenv("NOTION_TOKEN", "test-token")
    assert await assistant.run_skill("notion", {"query": "nova"}) == "- Pomysły na Nova"
    read = await assistant.run_skill("notion", {"action": "read", "query": "nova"})
    assert read == "Pomysły na Nova\n\nParry\n☐ Co-op na 4 graczy"
    assert "Nic w Notion" in await assistant.run_skill("notion", {"query": "nic"})

    added = await assistant.run_skill(
        "notion", {"action": "add", "title": "Bossowie", "text": "Smok\n\nGolem"}
    )
    assert added == "Dodane do Notion: Bossowie."
    method, _, body = calls[-1]
    assert method == "POST" and body["parent"] == {"page_id": "abc123"}
    assert len(body["children"]) == 2
    assert dia.store.audit(action="notion.add")[0]["detail"] == "Bossowie"
