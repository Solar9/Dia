"""Emergency stop and the quiet / screen / camera switches (state.json)."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from dia.core import processes
from dia.core.jsonfile import read_json, write_json

if TYPE_CHECKING:
    from dia.core.orchestrator import Orchestrator

log = logging.getLogger("dia")


class RunState:
    def __init__(self, dia: Orchestrator) -> None:
        self.dia = dia
        self._state_path = dia.config.data_dir / "state.json"

    def _read_state(self) -> dict[str, Any]:
        state: dict[str, Any] = read_json(self._state_path, {})
        return state

    def _write_state(self, **changes: Any) -> None:
        state = {**self._read_state(), **changes}
        write_json(self._state_path, state)

    async def stop_all(self, reason: str = "") -> list[str]:
        """Emergency stop: end every running agent and test now, and start nothing new
        (queued tasks, schedules, watchers) until :meth:`resume`. Survives restarts."""
        self.dia.halted = True
        self._write_state(halted=True)
        stopped = processes.stop_all()
        self.dia._wake.set()  # tasks waiting for a usage limit give up too
        self.dia._wake = asyncio.Event()
        self.dia.audit("dia.stop", None, reason or f"{len(stopped)} process(es)")
        await self.dia.emit(
            "stop", None, f"stopped {len(stopped)} process(es)", {"stopped": stopped}
        )
        return stopped

    async def resume(self) -> None:
        self.dia.halted = False
        self._write_state(halted=False)
        self.dia.audit("dia.resume")
        await self.dia.emit("resume", None, "resumed")

    @property
    def quiet(self) -> bool:
        """Quiet mode: Dia answers in text only (while you work, game or sleep)."""
        return bool(self._read_state().get("quiet"))

    def set_quiet(self, on: bool) -> None:
        self._write_state(quiet=on)
        self.dia.audit("dia.quiet", None, "on" if on else "off")
        self.dia.spawn(self.dia.emit("quiet", None, "on" if on else "off"))

    @property
    def screen_enabled(self) -> bool:
        """Screen awareness: off unless you switched it on (see dia.screen)."""
        return bool(self._read_state().get("screen"))

    def set_screen(self, on: bool) -> None:
        self._write_state(screen=on)
        self.dia.audit("screen.access", None, "on" if on else "off")
        self.dia.spawn(
            self.dia.emit("screen", None, "on" if on else "off", {"state": "on" if on else "off"})
        )

    @property
    def camera_enabled(self) -> bool:
        """The camera: off unless you switched it on (see dia.camera)."""
        return bool(self._read_state().get("camera"))

    def set_camera(self, on: bool) -> None:
        self._write_state(camera=on)
        self.dia.audit("camera.access", None, "on" if on else "off")
        self.dia.spawn(
            self.dia.emit("camera", None, "on" if on else "off", {"state": "on" if on else "off"})
        )
