"""Push notifications to the installed app (phone or desktop), even when it is closed.

Standard Web Push: the browser gives Dia a subscription, Dia signs messages
with its own VAPID key (``<data_dir>/vapid.pem``, mode 600) and the browser
vendor's push service delivers them. Message bodies are end-to-end encrypted
to the subscribed device. Needs ``pip install 'dia[push]'`` and an HTTPS
address for the app (e.g. ``tailscale serve``; see docs/MOBILE.md).

``[push]``::

    [push]
    events = ["task", "ci", "watch", "review", "learn", "limit", "schedule", "issue"]
    subject = "mailto:you@example.com"   # contact for push services
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dia.attention import Attention

if TYPE_CHECKING:
    from dia.orchestrator import Event, Orchestrator
    from dia.store import TaskRecord

log = logging.getLogger("dia.push")

DEFAULT_EVENTS = [
    "task",
    "ci",
    "watch",
    "review",
    "learn",
    "limit",
    "schedule",
    "issue",
    "system",
    "mission",
    "build",
    "security",
    "digest",
    "suggestion",
    "goal",
    "benchmark",
]
_FINAL = ("done", "failed")


def available() -> bool:
    try:
        import pywebpush  # noqa: F401
    except ImportError:
        return False
    return True


class Push:
    def __init__(self, dia: Orchestrator) -> None:
        self.dia = dia
        self._statuses: dict[str, str] = {}

    @property
    def options(self) -> dict[str, Any]:
        return self.dia.config.section("push")

    @property
    def key_path(self) -> Path:
        return self.dia.config.data_dir / "vapid.pem"

    @property
    def subs_path(self) -> Path:
        return self.dia.config.data_dir / "push.json"

    # --------------------------------------------------------------- keys ---

    def public_key(self) -> str:
        """The application server key the browser subscribes with (base64url)."""
        from cryptography.hazmat.primitives import serialization
        from py_vapid import Vapid01, b64urlencode

        if self.key_path.exists():
            vapid = Vapid01.from_file(str(self.key_path))
        else:
            vapid = Vapid01()
            vapid.generate_keys()
            self.key_path.parent.mkdir(parents=True, exist_ok=True)
            self.key_path.touch(mode=0o600)
            self.key_path.write_bytes(vapid.private_pem())
        raw = vapid.public_key.public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        return b64urlencode(raw)

    # ------------------------------------------------------ subscriptions ---

    def subscriptions(self) -> list[dict[str, Any]]:
        try:
            return json.loads(self.subs_path.read_text())
        except (OSError, ValueError):
            return []

    def _save(self, subs: list[dict[str, Any]]) -> None:
        self.subs_path.parent.mkdir(parents=True, exist_ok=True)
        self.subs_path.touch(mode=0o600, exist_ok=True)
        self.subs_path.write_text(json.dumps(subs, indent=2))

    def subscribe(self, subscription: dict[str, Any], device: str | None) -> None:
        endpoint = subscription.get("endpoint", "")
        keys = subscription.get("keys", {})
        if not endpoint.startswith("https://") or not keys.get("p256dh") or not keys.get("auth"):
            raise ValueError("not a push subscription")
        subs = [s for s in self.subscriptions() if s["endpoint"] != endpoint]
        subs.append(
            {
                "endpoint": endpoint,
                "keys": {"p256dh": keys["p256dh"], "auth": keys["auth"]},
                "device": device or "this computer",
                "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
            }
        )
        self._save(subs)

    def unsubscribe(self, endpoint: str) -> bool:
        subs = self.subscriptions()
        kept = [s for s in subs if s["endpoint"] != endpoint]
        self._save(kept)
        return len(kept) != len(subs)

    def forget_device(self, device: str) -> None:
        """A revoked device stops getting notifications too."""
        self._save([s for s in self.subscriptions() if s.get("device") != device])

    # ------------------------------------------------------------ sending ---

    def _send_one(self, sub: dict[str, Any], payload: str) -> bool:
        """Deliver to one subscription; False when it is gone for good."""
        from pywebpush import WebPushException, webpush

        subject = self.options.get("subject", "https://github.com/Solar9/Dia")
        try:
            webpush(
                {"endpoint": sub["endpoint"], "keys": sub["keys"]},
                data=payload,
                vapid_private_key=str(self.key_path),
                vapid_claims={"sub": subject},
                ttl=int(self.options.get("ttl", 3600)),
                timeout=10,
            )
        except WebPushException as exc:
            status = getattr(exc.response, "status_code", None)
            if status in (404, 410):
                return False
            log.warning("push to %s failed: %s", sub.get("device"), exc)
        return True

    async def send(self, title: str, body: str, url: str = "/", tag: str | None = None) -> int:
        subs = self.subscriptions()
        if not subs:
            return 0
        self.public_key()  # make sure the key exists
        payload = json.dumps({"title": title, "body": body[:400], "url": url, "tag": tag})
        results = await asyncio.gather(
            *(asyncio.to_thread(self._send_one, sub, payload) for sub in subs)
        )
        gone = [s["endpoint"] for s, alive in zip(subs, results, strict=True) if not alive]
        for endpoint in gone:
            self.unsubscribe(endpoint)
        return len(subs) - len(gone)

    # ------------------------------------------------------------- events ---

    def wants(self, kind: str) -> bool:
        return kind in self.options.get("events", DEFAULT_EVENTS)

    async def on_event(self, event: Event) -> None:
        if event.kind == "voice" or not self.wants(event.kind):
            return
        task = event.task
        title = {
            "ci": "CI",
            "watch": "Build",
            "review": "Review",
            "learn": "Dia: worth remembering?",
            "limit": "Usage limit",
            "schedule": event.data.get("job", {}).get("name") or "Dia",
            "issue": "New issue",
            "system": "Computer",
            "build": "Build",
            "mission": "Mission",
            "suggestion": "Dia suggests",
            "goal": "Goal review",
            "benchmark": "Benchmark",
        }.get(event.kind, "Dia")
        if task and event.kind != "schedule":
            title += f" · {task.project}"
        if event.kind == "digest":
            title = "Dia: while it was quiet"
        url = f"/#task={task.id}" if task else "/"
        if event.kind != "digest" and not Attention(self.dia).admit(
            event.kind, title, event.message
        ):
            return  # quiet hours or the day's budget: held for the summary
        await self.send(title, event.message, url, tag=f"{event.kind}-{task.id if task else ''}")

    def on_task_saved(self, task: TaskRecord) -> None:
        """Push when a task finishes (or a plan is ready), once per status."""
        if not self.wants("task") or task.mode == "check":
            return
        previous = self._statuses.get(task.id)
        self._statuses[task.id] = task.status
        if task.status not in _FINAL or previous == task.status or previous is None:
            return
        icon = {"done": "✅", "failed": "❌"}[task.status]
        body = (task.summary or task.error or task.prompt).strip().splitlines()[0][:200]
        title = f"{icon} {task.project}: {task.prompt.splitlines()[0][:60]}"
        if not Attention(self.dia).admit("task", title, body):
            return
        self.dia.spawn(self.send(title, body, f"/#task={task.id}", tag=f"task-{task.id}"))
