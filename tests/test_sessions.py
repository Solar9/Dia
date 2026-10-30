import json
import sqlite3
from pathlib import Path

from dia.sessions import _kind_of, _option, find_sessions, parse_transcript


def test_cli_commands_are_recognised_even_behind_a_runtime() -> None:
    assert _kind_of(["/home/u/.local/bin/claude", "--model", "opus"]) == "claude-code"
    assert _kind_of(["node", "/usr/lib/node_modules/@openai/codex/bin/codex"]) == "codex"
    assert _kind_of(["/home/u/.local/bin/cursor-agent"]) == "cursor"
    assert _kind_of(["/usr/bin/agent"]) is None  # a common word, not Cursor's
    assert _kind_of(["node", "/x/@openai/codex/bin/codex.js"]) == "codex"  # script extension
    assert _kind_of(["/usr/lib/x/vendor/codex"], "/usr/lib/x/vendor/codex") == "codex"
    assert _kind_of(["bash", "-c", "ls"]) is None


def test_model_and_session_are_read_from_the_command_line() -> None:
    argv = ["claude", "--model=opus", "--resume", "abc"]
    assert _option(argv, ("--model", "-m")) == "opus"
    assert _option(argv, ("--resume",)) == "abc"


def test_scanning_the_process_table_does_not_fail() -> None:
    assert isinstance(find_sessions(), list)


def test_claude_code_transcript(tmp_path: Path) -> None:
    lines = [
        {"type": "user", "timestamp": "2026-10-28T14:15:00Z",
         "message": {"role": "user", "content": "hej"}},
        {"type": "assistant", "timestamp": "2026-10-28T14:15:05Z",
         "message": {"role": "assistant", "content": [
            {"type": "text", "text": "cześć"}, {"type": "tool_use", "name": "Bash"}]}},
        {"type": "user", "timestamp": "2026-10-28T14:16:00Z",
         "message": {"role": "user", "content": "dalej"}},
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "text", "text": "ok"}]}},
        {"type": "user", "isSidechain": True, "message": {"role": "user", "content": "side"}},
        {"type": "user", "message": {"role": "user", "content": "<command-name>/x</command-name>"}},
    ]  # fmt: skip
    f = tmp_path / "s.jsonl"
    f.write_text("\n".join(json.dumps(x) for x in lines) + "\nnot json\n")
    found = parse_transcript(f)
    assert [(m["role"], m["text"], m["at"]) for m in found] == [
        ("user", "hej", "2026-10-28T14:15:00Z"),
        ("assistant", "cześć", "2026-10-28T14:15:05Z"),
        ("user", "dalej", "2026-10-28T14:16:00Z"),
        ("assistant", "ok", "2026-10-28T14:16:00Z"),
    ]


def test_codex_transcript(tmp_path: Path) -> None:
    def item(role, kind, text, ts):
        content = [{"type": kind, "text": text}]
        payload = {"type": "message", "role": role, "content": content}
        return {"type": "response_item", "timestamp": ts, "payload": payload}

    lines = [
        {"type": "session_meta", "payload": {"cwd": "/x"}},
        item(
            "user",
            "input_text",
            "<environment_context>cwd</environment_context>",
            "2026-10-28T14:20:00Z",
        ),
        item("user", "input_text", "sprawdź Dia", "2026-10-28T14:20:01Z"),
        item("assistant", "output_text", "sprawdzam", "2026-10-28T14:20:08Z"),
    ]
    f = tmp_path / "rollout-1.jsonl"
    f.write_text("\n".join(json.dumps(x) for x in lines))
    found = parse_transcript(f)
    assert [m["text"] for m in found] == ["sprawdź Dia", "sprawdzam"]
    assert [m["at"] for m in found] == ["2026-10-28T14:20:01Z", "2026-10-28T14:20:08Z"]


def test_cursor_transcript(tmp_path: Path) -> None:
    f = tmp_path / "store.db"
    db = sqlite3.connect(f)
    db.execute("CREATE TABLE blobs (id TEXT, data BLOB)")
    reply = {"role": "assistant", "content": [{"type": "text", "text": "yo"}]}
    for data in (b"\x00binary", json.dumps({"role": "user", "content": "hi"}).encode(),
                 json.dumps(reply).encode()):  # fmt: skip
        db.execute("INSERT INTO blobs VALUES ('x', ?)", (data,))
    db.commit()
    db.close()
    assert [m["text"] for m in parse_transcript(f)] == ["hi", "yo"]


def test_cursor_message_keeps_its_timestamp(tmp_path: Path) -> None:
    f = tmp_path / "store.db"
    db = sqlite3.connect(f)
    db.execute("CREATE TABLE blobs (id TEXT, data BLOB)")
    user = {"role": "user", "content": "hi", "createdAt": "2026-10-28T15:01:00Z"}
    db.execute("INSERT INTO blobs VALUES ('x', ?)", (json.dumps(user).encode(),))
    db.commit()
    db.close()
    found = parse_transcript(f)
    assert found[0]["at"] == "2026-10-28T15:01:00Z"


def test_cursor_assistant_inherits_the_user_timestamp(tmp_path: Path) -> None:
    f = tmp_path / "store.db"
    db = sqlite3.connect(f)
    db.execute("CREATE TABLE blobs (id TEXT, data BLOB)")
    user = {
        "role": "user",
        "content": "<timestamp>Friday, Oct 30, 2026, 10:23 AM (UTC+1)</timestamp>\n"
        "<user_query>\ntestuj\n</user_query>",
    }
    reply = {"role": "assistant", "content": [{"type": "text", "text": "ok"}]}
    db.execute("INSERT INTO blobs VALUES ('u', ?)", (json.dumps(user).encode(),))
    db.execute("INSERT INTO blobs VALUES ('a', ?)", (json.dumps(reply).encode(),))
    db.commit()
    db.close()
    found = parse_transcript(f)
    assert [(m["role"], m["text"]) for m in found] == [("user", "testuj"), ("assistant", "ok")]
    assert found[0]["at"] == "Friday, Oct 30, 2026, 10:23 AM (UTC+1)"
    assert found[1]["at"] == found[0]["at"]


def test_agent_commands_cover_each_cli() -> None:
    from dia.sessions import RESUME_HINT, agent_commands

    for kind in RESUME_HINT:
        rows = agent_commands(kind, "pl")
        cmds = {c["cmd"] for c in rows}
        assert {"/help", "/model", "/status", "/release"} <= cmds
        assert any(c["help"] for c in rows)
        assert next(c for c in rows if c["cmd"] == "/help")["local"] is True
        assert next(c for c in rows if c["cmd"] == "/compact")["local"] is False
    assert "/permissions" in {c["cmd"] for c in agent_commands("claude-code")}
    assert "/mode" in {c["cmd"] for c in agent_commands("cursor")}
    assert "/approvals" in {c["cmd"] for c in agent_commands("codex")}


def test_session_ids_and_files_are_found_again(tmp_path: Path, monkeypatch) -> None:
    from dia import sessions

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    claude = tmp_path / ".claude" / "projects" / "-x" / "abc-123.jsonl"
    claude.parent.mkdir(parents=True)
    claude.write_text("{}")
    assert sessions.session_id_of("claude-code", claude) == "abc-123"
    assert sessions.file_of("claude-code", "abc-123") == claude
    rollout = tmp_path / ".codex" / "sessions" / "2026" / "10" / "27" / "rollout-1-aaaa.jsonl"
    rollout.parent.mkdir(parents=True)
    rollout.write_text(json.dumps({"type": "session_meta", "payload": {"id": "aaaa"}}))
    assert sessions.session_id_of("codex", rollout) == "aaaa"
    assert sessions.file_of("codex", "aaaa") == rollout
    store = tmp_path / ".cursor" / "chats" / "h" / "cid" / "store.db"
    store.parent.mkdir(parents=True)
    store.write_text("")
    assert sessions.session_id_of("cursor", store) == "cid"
    assert sessions.file_of("cursor", "cid") == store


def test_captured_sessions_are_kept_and_released(tmp_path: Path) -> None:
    from dia.sessions import Captured, CapturedStore

    store = CapturedStore(tmp_path / "c.json")
    assert store.all() == []
    store.add(Captured(id="a", kind="claude-code", cwd="/x"))
    store.add(Captured(id="b", kind="codex", cwd="/y"))
    assert store.get("b").resume == "codex resume b"
    store.replace_id("a", "a2")
    assert [c.id for c in store.all()] == ["a2", "b"]
    store.remove("a2")
    assert [c.id for c in store.all()] == ["b"]
    store.update("b", model="gpt-5", web=True, mode="read-only")
    item = store.get("b")
    assert item.model == "gpt-5" and item.web and item.mode == "read-only"
    (tmp_path / "c.json").write_text(
        json.dumps([{"id": "x", "kind": "cursor", "cwd": "/z", "unknown": True}])
    )
    loaded = CapturedStore(tmp_path / "c.json").get("x")
    assert loaded.cwd == "/z" and not hasattr(loaded, "unknown")


def test_only_what_you_typed_is_shown() -> None:
    from dia.sessions import _message

    cursor = (
        "<timestamp>Wednesday, Oct 28, 2026, 3:15 PM (UTC+1)</timestamp>\n"
        "<user_query>\nznowu chyba openlogi wisi?\n</user_query>"
    )
    shown = _message("user", cursor)
    assert shown["text"] == "znowu chyba openlogi wisi?"
    assert shown["at"] == "Wednesday, Oct 28, 2026, 3:15 PM (UTC+1)"
    added = "<timestamp>now</timestamp>\n<system_reminder>be nice</system_reminder>\nhello"
    assert _message("user", added)["text"] == "hello"
    # Cursor's first turn is only auto context (git status, rules, skills…) — hide it,
    # including leftovers that sit outside <rules> and used to leak as a "user" bubble.
    context = (
        "<user_info>\nOS Version: linux\n</user_info>\n"
        "<git_status>\n## ui_v2.0\n M app.js\n</git_status>\n"
        "<agent_transcripts>\npast chats\n</agent_transcripts>\n"
        "<rules>\n<user_rules>\nAnalyze all staged changes\n</user_rules>\n</rules>\n"
        "<available_subagent_types>\ngeneralPurpose: …\n</available_subagent_types>\n"
        "<agent_skills>\n…\n</agent_skills>\n"
        "<dynamic_tools>\n…\n</dynamic_tools>"
    )
    assert _message("user", context) is None
    # Real query may follow the same auto context in one blob — show only the query
    with_query = context + "\n<user_query>\njaki jest aktualny stan repo?\n</user_query>"
    assert _message("user", with_query)["text"] == "jaki jest aktualny stan repo?"
    # Codex: AGENTS.md + environment as the first "user" turn — hide it
    agents = (
        "# AGENTS.md instructions\n\n<INSTRUCTIONS>\n# Ultraviolet\nnie commituj tego\n"
        "</INSTRUCTIONS>\n<environment_context>\n  <cwd>/x</cwd>\n</environment_context>"
    )
    assert _message("user", agents) is None
    # Codex may glue the real prompt after the wrappers in one message
    glued = agents + "\njaki jest stan repo?"
    assert _message("user", glued)["text"] == "jaki jest stan repo?"
    # an answer that talks about such tags is left as it is
    assert "<user_query>" in _message("assistant", "use <user_query> tags")["text"]


def test_codex_agents_md_turn_is_hidden(tmp_path: Path) -> None:
    def item(role, kind, text):
        content = [{"type": kind, "text": text}]
        payload = {"type": "message", "role": role, "content": content}
        return {"type": "response_item", "payload": payload}

    agents = (
        "# AGENTS.md instructions\n\n<INSTRUCTIONS>\nrules\n</INSTRUCTIONS>\n"
        "<environment_context><cwd>/x</cwd></environment_context>"
    )
    lines = [
        item("user", "input_text", agents),
        item("user", "input_text", "jaki jest stan repo?"),
        item("assistant", "output_text", "na ui_v2.0"),
    ]
    f = tmp_path / "rollout-agents.jsonl"
    f.write_text("\n".join(json.dumps(x) for x in lines))
    assert [m["text"] for m in parse_transcript(f)] == ["jaki jest stan repo?", "na ui_v2.0"]
