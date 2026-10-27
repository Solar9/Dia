"""Paired devices (your phone...) that may use Dia's API from elsewhere.

Each device gets its own token, shown once when it is paired; Dia keeps only
its SHA-256 in ``<data_dir>/devices.json`` (mode 600). Revoking a device
removes it, and its token stops working at once.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path


def public_url(ui: dict, port: int) -> str | None:
    """Where a paired device opens Dia: ``[ui] public_url``, else the first ``listen``
    address; None when remote access is not set up."""
    if url := ui.get("public_url"):
        return url.rstrip("/") + "/"
    listen = [a for a in ui.get("listen", []) if a not in ("127.0.0.1", "localhost")]
    return f"http://{listen[0]}:{port}/" if listen else None


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class Device:
    id: str
    name: str
    token_hash: str
    created_at: str
    last_seen: str | None = None
    # The owner's own phone may change settings and run Dia's tools too; never
    # secrets or pairing (set from the computer only).
    full: bool = False


class Devices:
    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / "devices.json"

    def list(self) -> list[Device]:
        try:
            return [Device(**d) for d in json.loads(self.path.read_text())]
        except (OSError, ValueError, TypeError):
            return []

    def _write(self, devices: list[Device]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(mode=0o600, exist_ok=True)
        self.path.chmod(0o600)
        self.path.write_text(json.dumps([asdict(d) for d in devices], indent=2))

    def pair(self, name: str) -> tuple[Device, str]:
        """A new device and its token (the only time the token is visible)."""
        token = "dev_" + secrets.token_urlsafe(32)
        device = Device(secrets.token_hex(4), name, _hash(token), _now())
        self._write([*self.list(), device])
        return device, token

    def revoke(self, key: str) -> Device | None:
        """Remove a device by id or name."""
        devices = self.list()
        gone = next((d for d in devices if key in (d.id, d.name)), None)
        if gone:
            self._write([d for d in devices if d is not gone])
        return gone

    def set_full(self, key: str, full: bool) -> Device | None:
        devices = self.list()
        device = next((d for d in devices if key in (d.id, d.name)), None)
        if device:
            device.full = full
            self._write(devices)
        return device

    def authenticate(self, token: str) -> Device | None:
        if not token.startswith("dev_"):
            return None
        digest = _hash(token)
        devices = self.list()
        for device in devices:
            if secrets.compare_digest(device.token_hash, digest):
                now = _now()
                if (device.last_seen or "")[:16] != now[:16]:  # at most once a minute
                    device.last_seen = now
                    self._write(devices)
                return device
        return None
