"""Agent CLIs running on this machine, started by Dia or by hand in a terminal.

Found by scanning the process table (``/proc``), so it needs nothing from the
agents themselves and works for every CLI Dia knows. A session's conversation
is read from the transcript file its CLI keeps (Claude Code: ``~/.claude``,
Codex: ``~/.codex``, Cursor Agent: ``~/.cursor``); nothing is written, and
only files of listed sessions are ever opened.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from dia import processes

# executable name -> agent kind (the plugin name used in [agents.*] type = ...)
_KINDS = {"claude": "claude-code", "codex": "codex", "cursor-agent": "cursor", "agent": "cursor"}
_WRAPPERS = {"node", "bun", "deno", "python", "python3", "npx", "sh", "bash"}  # shipped as scripts
_EXTENSIONS = (".js", ".mjs", ".cjs", ".exe", ".py")
MAX_MESSAGES = 40
MAX_TEXT = 4000
TAIL_BYTES = 2_000_000
_MODEL_FLAGS = ("--model", "-m")


@dataclass
class CliSession:
    pid: int
    kind: str
    cwd: Path | None
    age_s: float
    model: str | None
    session_id: str | None
    from_dia: bool  # started by Dia (itself or a child of one of its agents)
    has_transcript: bool = False


def _read(pid: int, name: str) -> bytes:
    try:
        return Path(f"/proc/{pid}/{name}").read_bytes()
    except OSError:
        return b""


def _stat(pid: int) -> tuple[int, int] | None:
    """(parent pid, start time in clock ticks) from /proc/<pid>/stat."""
    raw = _read(pid, "stat").decode(errors="replace")
    if ")" not in raw:
        return None
    rest = raw.rsplit(")", 1)[1].split()
    try:
        return int(rest[1]), int(rest[19])
    except (IndexError, ValueError):
        return None


def _name(path: str) -> str:
    name = os.path.basename(path)
    for ext in _EXTENSIONS:
        name = name.removesuffix(ext)
    return name


def _kind_of(argv: list[str], exe: str = "") -> str | None:
    """The agent kind a command line belongs to, if it is one of the known CLIs."""
    if not argv:
        return None
    candidates = [_name(argv[0])]
    if candidates[0] in _WRAPPERS:  # a script run by node, bun, ...: its first words
        candidates += [_name(a) for a in argv[1:4] if not a.startswith("-")]
    if exe:
        candidates.append(_name(exe))
    for name in candidates:
        kind = _KINDS.get(name)
        # "agent" is a common word: only Cursor's if the path says so.
        if kind and (name != "agent" or "cursor" in " ".join([*argv, exe]).lower()):
            return kind
    return None


def _option(argv: list[str], flags: tuple[str, ...]) -> str | None:
    for i, arg in enumerate(argv):
        for flag in flags:
            if arg == flag and i + 1 < len(argv):
                return argv[i + 1]
            if arg.startswith(flag + "="):
                return arg.split("=", 1)[1]
    return None


def find_sessions(proc_root: str = "/proc") -> list[CliSession]:
    """Every running agent CLI, outermost process only (their helpers are skipped)."""
    if proc_root != "/proc" or not os.path.isdir(proc_root):
        return []
    me = os.getpid()
    ticks = os.sysconf("SC_CLK_TCK")
    try:
        boot = float(Path("/proc/uptime").read_text().split()[0])
    except (OSError, ValueError, IndexError):
        boot = 0.0
    owned = set(processes.running())
    found: dict[int, tuple[str, list[str], int, int]] = {}
    parents: dict[int, int] = {}
    for entry in os.listdir(proc_root):
        if not entry.isdigit() or int(entry) == me:
            continue
        pid = int(entry)
        stat = _stat(pid)
        if stat is None:
            continue
        parents[pid] = stat[0]
        argv = [a for a in _read(pid, "cmdline").decode(errors="replace").split("\0") if a]
        try:
            exe = os.readlink(f"/proc/{pid}/exe")
        except OSError:
            exe = ""
        if kind := _kind_of(argv, exe):
            found[pid] = (kind, argv, *stat)
    sessions = []
    for pid, (kind, argv, ppid, started) in found.items():
        if ppid in found and found[ppid][0] == kind:
            continue  # a helper of an agent already listed
        chain, cur = set(), pid
        while cur and cur not in chain:
            chain.add(cur)
            cur = parents.get(cur, 0)
        try:
            cwd: Path | None = Path(os.readlink(f"/proc/{pid}/cwd"))
        except OSError:
            cwd = None
        sessions.append(
            CliSession(
                pid=pid,
                kind=kind,
                cwd=cwd,
                age_s=max(0.0, boot - started / ticks) if boot else 0.0,
                model=_option(argv, _MODEL_FLAGS),
                session_id=_option(argv, ("--resume", "-r", "--session-id")),
                from_dia=bool(chain & owned),
            )
        )
    for session in sessions:
        session.has_transcript = transcript_file(session) is not None
    return sorted(sessions, key=lambda s: s.age_s)


# ------------------------------------------------------------ transcripts ---


def _open_files(pid: int) -> list[Path]:
    found = []
    try:
        for fd in os.listdir(f"/proc/{pid}/fd"):
            try:
                found.append(Path(os.readlink(f"/proc/{pid}/fd/{fd}")))
            except OSError:
                continue
    except OSError:
        pass
    return found


def _newest(files: list[Path]) -> Path | None:
    files = [f for f in files if f.is_file()]
    return max(files, key=lambda f: f.stat().st_mtime, default=None)


def _claude_file(session: CliSession) -> Path | None:
    root = Path.home() / ".claude" / "projects"
    if session.session_id and (hit := _newest(list(root.glob(f"*/{session.session_id}.jsonl")))):
        return hit
    held = [f for f in _open_files(session.pid) if f.suffix == ".jsonl" and root in f.parents]
    if hit := _newest(held):
        return hit
    if session.cwd is None:
        return None
    return _newest(list((root / re.sub(r"[^A-Za-z0-9]", "-", str(session.cwd))).glob("*.jsonl")))


def _codex_cwd(path: Path) -> str | None:
    try:
        with path.open(errors="replace") as f:
            meta = json.loads(f.readline())
    except (OSError, ValueError):
        return None
    return (meta.get("payload") or meta).get("cwd")


def _codex_file(session: CliSession) -> Path | None:
    root = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "sessions"
    held = [f for f in _open_files(session.pid) if f.name.startswith("rollout-")]
    if hit := _newest(held):
        return hit
    if session.cwd is None:
        return None
    recent = sorted(root.glob("*/*/*/rollout-*.jsonl"), key=lambda f: f.stat().st_mtime)[-60:]
    return _newest([f for f in recent if _codex_cwd(f) == str(session.cwd)])


def _cursor_file(session: CliSession) -> Path | None:
    """Cursor Agent keeps a chat as ``~/.cursor/chats/<md5 of the folder>/<id>/store.db``."""
    root = Path.home() / ".cursor" / "chats"
    held = [f for f in _open_files(session.pid) if f.name == "store.db" and root in f.parents]
    if hit := _newest(held):
        return hit
    if session.cwd is None:
        return None
    folder = root / hashlib.md5(str(session.cwd).encode()).hexdigest()  # noqa: S324
    return _newest(list(folder.glob("*/store.db")))


def transcript_file(session: CliSession) -> Path | None:
    try:
        if session.kind == "claude-code":
            return _claude_file(session)
        if session.kind == "codex":
            return _codex_file(session)
        if session.kind == "cursor":
            return _cursor_file(session)
    except OSError:
        pass
    return None


def _text(content: object, kinds: tuple[str, ...]) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") in kinds
        ]
        return "\n".join(p for p in parts if p)
    return ""


_NOISE = ("<environment_context>", "<user_instructions>", "<command-", "<local-command", "Caveat:")


def _message(role: object, text: str, at: object = "") -> dict[str, str] | None:
    text = text.strip()
    if role not in ("user", "assistant") or not text or text.startswith(_NOISE):
        return None
    return {"role": str(role), "text": text[:MAX_TEXT], "at": str(at or "")}


def _cursor_messages(path: Path) -> list[dict[str, str]]:
    """Cursor Agent's store.db: JSON message blobs among other blobs, in insertion order."""
    out: list[dict[str, str]] = []
    try:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1)
        try:
            rows = db.execute("SELECT data FROM blobs ORDER BY rowid").fetchall()
        finally:
            db.close()
    except sqlite3.Error:
        return []
    for (data,) in rows:
        try:
            obj = json.loads(data)
        except (ValueError, TypeError):
            continue  # not a message (binary structure blobs)
        if isinstance(obj, dict) and (
            m := _message(obj.get("role"), _text(obj.get("content"), ("text",)))
        ):
            out.append(m)
    return out


def parse_transcript(path: Path, limit: int = MAX_MESSAGES) -> list[dict[str, str]]:
    """The last ``limit`` user and assistant messages of a CLI session's file."""
    if path.name == "store.db":
        return _cursor_messages(path)[-limit:]
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            f.seek(max(0, size - TAIL_BYTES))
            lines = f.read().decode(errors="replace").splitlines()
    except OSError:
        return []
    if size > TAIL_BYTES:
        lines = lines[1:]  # the first line is cut off
    out: list[dict[str, str]] = []
    for line in lines:
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if not isinstance(obj, dict) or obj.get("isSidechain"):
            continue
        if obj.get("type") in ("user", "assistant") and isinstance(obj.get("message"), dict):
            msg = obj["message"]  # Claude Code
            role, text = msg.get("role"), _text(msg.get("content"), ("text",))
        else:  # Codex: {"type": "response_item", "payload": {"type": "message", ...}}
            msg = obj.get("payload") if isinstance(obj.get("payload"), dict) else obj
            if msg.get("type") != "message":
                continue
            role, text = msg.get("role"), _text(msg.get("content"), ("input_text", "output_text"))
        if m := _message(role, text, obj.get("timestamp")):
            out.append(m)
    return out[-limit:]


# ------------------------------------------------- taking a session over ---
# "Capture": the app takes a terminal session over. The CLI process is ended
# (its conversation stays in its file), the app keeps the conversation and
# continues it with `--resume`; in a terminal it can be resumed again later.

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
RESUME_HINT = {
    "claude-code": "claude --resume {id}",
    "codex": "codex resume {id}",
    "cursor": "cursor-agent --resume {id}",
}


def session_id_of(kind: str, path: Path) -> str | None:
    """The conversation id a CLI knows a transcript file by."""
    if kind == "claude-code":
        return path.stem
    if kind == "cursor":
        return path.parent.name
    if kind == "codex":
        try:
            with path.open(errors="replace") as f:
                meta = json.loads(f.readline())
            if found := (meta.get("payload") or meta).get("id"):
                return str(found)
        except (OSError, ValueError, AttributeError):
            pass
        match = _UUID.search(path.name)
        return match.group(0) if match else None
    return None


def file_of(kind: str, session_id: str) -> Path | None:
    """The transcript file of a conversation, found by its id."""
    home = Path.home()
    if kind == "claude-code":
        return _newest(list((home / ".claude" / "projects").glob(f"*/{session_id}.jsonl")))
    if kind == "cursor":
        return _newest(list((home / ".cursor" / "chats").glob(f"*/{session_id}/store.db")))
    if kind == "codex":
        root = Path(os.environ.get("CODEX_HOME") or home / ".codex") / "sessions"
        return _newest(list(root.glob(f"*/*/*/rollout-*{session_id}.jsonl")))
    return None


@dataclass
class Captured:
    id: str  # the CLI's conversation id
    kind: str
    cwd: str
    model: str | None = None
    taken_at: str = ""

    @property
    def resume(self) -> str:
        return RESUME_HINT[self.kind].format(id=self.id)


class CapturedStore:
    """The sessions the app took over, kept in one small JSON file."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def all(self) -> list[Captured]:
        try:
            return [Captured(**row) for row in json.loads(self.path.read_text())]
        except (OSError, ValueError, TypeError):
            return []

    def get(self, session_id: str) -> Captured | None:
        return next((c for c in self.all() if c.id == session_id), None)

    def save(self, rows: list[Captured]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps([c.__dict__ for c in rows], indent=1))

    def add(self, item: Captured) -> None:
        self.save([c for c in self.all() if c.id != item.id] + [item])

    def remove(self, session_id: str) -> None:
        self.save([c for c in self.all() if c.id != session_id])

    def replace_id(self, old: str, new: str) -> None:
        rows = self.all()
        for c in rows:
            if c.id == old:
                c.id = new
        self.save(rows)


def _alive(pid: int) -> bool:
    state = _read(pid, "stat").decode(errors="replace").rsplit(")", 1)[-1].split()[:1]
    return bool(state) and state[0] != "Z"  # a zombie is already gone, only not collected


def end_process(pid: int, grace: float = 5.0) -> bool:
    """Ask a CLI process to quit (SIGTERM), SIGKILL if it ignores that; True once it is gone."""
    import signal
    import time

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        if not _alive(pid):
            return True
        time.sleep(0.1)
    try:
        os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    time.sleep(0.2)
    return not _alive(pid)
