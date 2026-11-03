"""Constants and helpers shared by the API route modules."""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict, cast

from aiohttp import web

from dia.core.devices import Device
from dia.core.store import TaskRecord
from dia.core.taskstate import decision_of

# The paired device making a request (None: the owner). aiohttp < 3.12 has no
# typed request keys; a plain string works there.
DEVICE = web.RequestKey("device", object) if hasattr(web, "RequestKey") else "device"

if TYPE_CHECKING:
    from dia.assistant import Assistant
    from dia.core.devices import Devices
    from dia.core.orchestrator import Orchestrator
    from dia.desktop.push import Push

    pass

log = logging.getLogger("dia.api")

STATIC = Path(__file__).resolve().parent.parent.parent / "ui" / "static"
DEFAULT_PORT = 8765
LOOPBACK = ("127.0.0.1", "localhost", "[::1]")
# What a paired device may not do: only the owner, at this computer, may.
OWNER_ONLY = (
    "/api/cli-sessions",
    "/api/cli-captured",
    "/api/cli-commands",
    "/api/config",
    "/api/voice/",
    "/api/devices",
    "/api/settings",
    "/api/secrets",
    "/api/preferences",
    "/api/profile",
    "/api/work",
    "/api/tidy",
    "/api/tools",
    "/api/desktop",
)
# What even a device with full access may not do: secrets and pairing stay at the computer.
NEVER_REMOTE = ("/api/devices", "/api/secrets", "/api/desktop")
# Dia's CLI commands the app runs for the owner, showing their output: what has
# no button of its own still works from the app (Status → Tools).
TOOLS = (
    "doctor", "agents", "sandbox", "brains", "limits", "issues", "check", "bench", "launch",
    "lab", "redteam", "changelog", "security", "usage", "howto", "learned", "decisions",
    "schedule", "suggestions", "work", "goal", "why", "impact", "debt",
)  # fmt: skip
# Sections whose changes need a restart (they are read when channels start).
RESTART_SECTIONS = ("channels", "ui", "watch", "issues")


def api_token(data_dir: Path) -> str:
    """The API token, created on first use (file mode 600)."""
    path = data_dir / "api-token"
    if path.exists():
        return path.read_text().strip()
    data_dir.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    path.write_text(token + "\n")
    path.chmod(0o600)
    return token


def user_themes_dir() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "dia" / "themes"


async def read_body(request: web.Request) -> Any:
    """The JSON body of a request, or {} when it has none."""
    return await request.json() if request.can_read_body else {}


class _TaskFields(TypedDict):
    """Every field of TaskRecord."""

    id: str
    project: str
    agent: str
    mode: str
    prompt: str
    status: str
    branch: str | None
    commit_sha: str | None
    tests_ok: bool | None
    summary: str | None
    error: str | None
    details: dict[str, Any]
    created_at: str
    finished_at: str | None


class TaskJson(_TaskFields, total=False):
    """A task as the API sends it; the list and detail calls add the last two."""

    has_test_log: bool
    diffstat: dict[str, int] | None
    # merge | plan | ci | comments | None: what the task asks of the owner (core.taskstate)
    decision: str | None


class DeviceJson(TypedDict):
    """A paired device as the API sends it: the token's hash never leaves."""

    id: str
    name: str
    created_at: str
    last_seen: str | None
    full: bool


def task_json(task: TaskRecord) -> TaskJson:
    return cast(TaskJson, {**asdict(task), "decision": decision_of(task)})


def device_json(device: Device) -> DeviceJson:
    return cast(DeviceJson, {k: v for k, v in asdict(device).items() if k != "token_hash"})


def pairing(device: Device, token: str, public_url: str | None) -> dict[str, Any]:
    """What the owner needs to set up a device: its token, the link with the token,
    and that link as a QR code (SVG, when the optional ``qrcode`` package is there)."""
    url = f"{public_url}#token={token}" if public_url else None
    result: dict[str, Any] = {"device": device_json(device), "token": token, "url": url}
    if url:
        result["qr_svg"] = qr_svg(url)
    return result


def qr_svg(text: str) -> str | None:
    try:
        import qrcode
        import qrcode.image.svg
    except ImportError:
        return None
    image = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage, box_size=8)
    return image.to_string(encoding="unicode")


def _models_of(kind: str) -> tuple[str, ...]:
    from dia.core import plugins

    try:
        return getattr(plugins.load("dia.agents", kind), "models", ())
    except Exception:
        return ()


def _sandbox_state(config: Any) -> str:
    """ "on", "off" (switched off) or "unavailable" (no working bubblewrap)."""
    from dia.core import sandbox

    try:
        return (
            "on" if sandbox.enabled(config) else ("off" if sandbox.bwrap_works() else "unavailable")
        )
    except RuntimeError:
        return "unavailable"


class ApiBase:
    """What the route mixins expect from ApiChannel: declared for type checkers only,
    ApiChannel sets and defines all of it."""

    dia: Orchestrator
    assistant: Assistant
    devices: Devices
    push: Push
    remote: bool
    voice_state: str
    _diff_stats: dict[tuple[str, str], dict[str, int] | None]
    _tool_lock: asyncio.Lock

    if TYPE_CHECKING:

        def public_url(self) -> str | None: ...
        def _spawn(self, coro: Any) -> asyncio.Task[Any]: ...
        async def _start(self, run: Any) -> TaskRecord: ...
        async def _broadcast(self, payload: dict[str, Any]) -> None: ...
        def _talk(self) -> Any: ...
