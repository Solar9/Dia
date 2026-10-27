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
        {"type": "user", "message": {"role": "user", "content": "hej"}, "timestamp": "t1"},
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "text", "text": "cześć"}, {"type": "tool_use", "name": "Bash"}]}},
        {"type": "user", "isSidechain": True, "message": {"role": "user", "content": "side"}},
        {"type": "user", "message": {"role": "user", "content": "<command-name>/x</command-name>"}},
    ]  # fmt: skip
    f = tmp_path / "s.jsonl"
    f.write_text("\n".join(json.dumps(x) for x in lines) + "\nnot json\n")
    assert [(m["role"], m["text"]) for m in parse_transcript(f)] == [
        ("user", "hej"), ("assistant", "cześć")]  # fmt: skip


def test_codex_transcript(tmp_path: Path) -> None:
    def item(role, kind, text):
        content = [{"type": kind, "text": text}]
        payload = {"type": "message", "role": role, "content": content}
        return {"type": "response_item", "payload": payload}

    lines = [
        {"type": "session_meta", "payload": {"cwd": "/x"}},
        item("user", "input_text", "<environment_context>cwd</environment_context>"),
        item("user", "input_text", "sprawdź Dia"),
        item("assistant", "output_text", "sprawdzam"),
    ]
    f = tmp_path / "rollout-1.jsonl"
    f.write_text("\n".join(json.dumps(x) for x in lines))
    assert [m["text"] for m in parse_transcript(f)] == ["sprawdź Dia", "sprawdzam"]


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
