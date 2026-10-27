"""One conversation across devices.

Every channel keeps its own way of naming who is talking: the desktop UI is
"ui", the phone is its paired device's name, voice is the recognised
speaker (or "default"), Discord is the user's id. All of them that are
you, the owner, are one conversation: ask on the phone, follow up at the
desk, say "tak" to a plan by voice that you asked for on Discord. The
recent turns and the plan waiting for your "yes" live here, shared by every
channel of the running Dia and kept across restarts.

    [assistant]
    one_conversation = true             # the default
    owner_ids = ["123456789012345678"]  # your Discord user id, your speaker name
    # history_turns = 6, history_minutes = 30 (as before)

Other people (another Discord user, a guest voice) keep their own
conversations, as before.

**Sessions.** Besides that one running conversation ("owner": voice,
Discord and the phone continue it), the app can hold separate chat
sessions, like threads: one about nova's combat, one about the Steam page.
Each keeps its whole transcript, its own context for follow-ups (not
forgotten after a pause) and its own plan waiting for a "yes". They are
stored here, so every device of yours sees the same list.
"""

from __future__ import annotations

import json
import secrets
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dia.orchestrator import Orchestrator

OWNER = "owner"
BUILTIN_OWNER = {"ui", "default", OWNER}
SESSION = "chat-"  # ids of chat sessions
MAX_MESSAGES = 500


class Conversations:
    def __init__(self, dia: Orchestrator) -> None:
        self.dia = dia
        self.path = dia.config.data_dir / "conversations.json"
        self._data: dict[str, dict[str, Any]] = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        try:
            data = json.loads(self.path.read_text())
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._data))
            tmp.chmod(0o600)
            tmp.replace(self.path)
        except OSError:
            pass  # the conversation still works in memory

    def owner_ids(self) -> set[str]:
        options = self.dia.config.assistant
        ids = set(BUILTIN_OWNER) | {str(i) for i in options.get("owner_ids", [])}
        try:
            from dia.devices import Devices

            devices = Devices(self.dia.config.data_dir).list()
            ids |= {d.name for d in devices}  # your paired devices
        except Exception:
            pass
        return ids

    def canonical(self, conversation: str | None) -> str:
        conversation = conversation or "default"
        if self.dia.config.assistant.get("one_conversation", True) is False:
            return conversation
        if conversation.startswith(SESSION):
            return conversation
        return OWNER if conversation in self.owner_ids() else conversation

    def _entry(self, conversation: str) -> dict[str, Any]:
        return self._data.setdefault(self.canonical(conversation), {"turns": [], "last": 0})

    def history(self, conversation: str) -> list[tuple[str, str]]:
        """Recent (user, Dia) turns; forgotten after ``history_minutes`` of silence."""
        entry = self._entry(conversation)
        idle = float(self.dia.config.assistant.get("history_minutes", 30)) * 60
        session = self.canonical(conversation).startswith(SESSION)  # a thread keeps its context
        if not session and entry["turns"] and time.time() - entry.get("last", 0) > idle:
            entry["turns"] = []
            self._save()
        return [(t[0], t[1]) for t in entry["turns"]]

    def add_turn(self, conversation: str, text: str, reply: str) -> list[tuple[str, str]]:
        keep = max(1, int(self.dia.config.assistant.get("history_turns", 6)))
        entry = self._entry(conversation)
        entry["turns"] = [*entry["turns"], [text[:500], reply[:500]]][-keep:]
        entry["last"] = time.time()
        self._save()
        return [(t[0], t[1]) for t in entry["turns"]]

    def pending_plan(self, conversation: str) -> str | None:
        return self._entry(conversation).get("pending_plan")

    def set_pending_plan(self, conversation: str, plan_id: str | None) -> None:
        entry = self._entry(conversation)
        if entry.get("pending_plan") != plan_id:
            entry["pending_plan"] = plan_id
            self._save()

    # ------------------------------------------------------------ sessions ---

    def add_message(self, conversation: str, sender: str, text: str, **extra: Any) -> None:
        """The transcript the app shows ("me" or "dia"), with a task or plan id."""
        entry = self._entry(conversation)
        message = {"from": sender, "text": text[:20000], "at": time.time()}
        message.update({k: v for k, v in extra.items() if v})
        entry["messages"] = [*entry.get("messages", []), message][-MAX_MESSAGES:]
        entry["last"] = time.time()
        if sender == "me" and not entry.get("title"):
            entry["title"] = " ".join(text.split())[:60]
        self._save()

    def messages(self, conversation: str) -> list[dict[str, Any]]:
        return list(self._entry(conversation).get("messages", []))

    def sessions(self) -> list[dict[str, Any]]:
        """The owner's conversation first, then chat sessions, the latest first."""
        self._entry(OWNER)
        found = []
        for key, entry in self._data.items():
            if key != OWNER and not key.startswith(SESSION):
                continue
            found.append(
                {
                    "id": key,
                    "title": entry.get("title") or "",
                    "main": key == OWNER,
                    "last": entry.get("last") or entry.get("created") or 0,
                    "messages": len(entry.get("messages", [])),
                    "pending_plan": entry.get("pending_plan"),
                    "provider": entry.get("provider") or "dia",
                    "model": entry.get("model") or "",
                }
            )
        sessions = sorted((s for s in found if not s["main"]), key=lambda s: -s["last"])
        return [s for s in found if s["main"]] + sessions

    def create(self, title: str = "", provider: str = "", model: str = "") -> str:
        key = f"{SESSION}{secrets.token_hex(4)}"
        default = str(self.dia.config.section("chat").get("default", "dia"))
        self._data[key] = {
            "turns": [],
            "messages": [],
            "title": title.strip()[:60],
            "created": time.time(),
            "last": time.time(),
            "provider": provider or default,
            "model": model,
        }
        self._save()
        return key

    def _session(self, key: str) -> dict[str, Any]:
        if key != OWNER and not key.startswith(SESSION) or key not in self._data:
            raise KeyError(f"no chat session {key}")
        return self._data[key]

    def rename(self, key: str, title: str) -> None:
        self._session(key)["title"] = title.strip()[:60]
        self._save()

    def engine(self, key: str) -> tuple[str, str]:
        """Who answers in this session: "dia" (the assistant) or a model provider."""
        entry = self._data.get(self.canonical(key), {})
        return entry.get("provider") or "dia", entry.get("model") or ""

    def set_engine(self, key: str, provider: str, model: str = "") -> None:
        if key == OWNER and provider != "dia":
            raise ValueError("the main conversation is Dia's (voice and Discord share it)")
        entry = self._session(key)
        entry["provider"], entry["model"] = provider, model
        self._save()

    def delete(self, key: str) -> None:
        """A session is gone with its transcript; the main conversation is only cleared."""
        self._session(key)
        if key == OWNER:
            self._data[OWNER] = {"turns": [], "messages": [], "last": 0}
        else:
            del self._data[key]
        self._save()
