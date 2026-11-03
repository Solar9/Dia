"""API routes: settings."""

from __future__ import annotations

import tomllib

from aiohttp import web

from dia.channels.api._util import (
    DEVICE,
    RESTART_SECTIONS,
    STATIC,
    ApiBase,
    _models_of,
    device_json,
    pairing,
    user_themes_dir,
)
from dia.core.config import ConfigError, parse_config, read_settings, save_settings
from dia.desktop.push import available as push_available


class SettingsRoutes(ApiBase):
    async def list_devices(self, request: web.Request) -> web.Response:
        return web.json_response(
            {
                "remote": self.remote,
                "public_url": self.public_url(),
                "devices": [device_json(d) for d in self.devices.list()],
            }
        )

    async def pair_device(self, request: web.Request) -> web.Response:
        name = str((await request.json()).get("name") or "phone")[:60]
        device, token = self.devices.pair(name)
        self.dia.audit("device.pair", device.id, device.name)
        return web.json_response(pairing(device, token, self.public_url()), status=201)

    async def update_device(self, request: web.Request) -> web.Response:
        """Full access for the owner's own phone: settings and tools, not secrets or pairing."""
        full = bool((await request.json()).get("full"))
        device = self.devices.set_full(request.match_info["id"], full)
        if not device:
            raise web.HTTPNotFound(text="no such device")
        self.dia.audit("device.full" if full else "device.limited", device.id, device.name)
        return web.json_response(device_json(device))

    async def revoke_device(self, request: web.Request) -> web.Response:
        device = self.devices.revoke(request.match_info["id"])
        if not device:
            raise web.HTTPNotFound(text="no such device")
        self.push.forget_device(device.name)
        self.dia.audit("device.revoke", device.id, device.name)
        return web.json_response({"message": "revoked"})

    async def get_settings(self, request: web.Request) -> web.Response:
        from dia.core import plugins
        from dia.persona import PRESETS

        config = self.dia.config
        return web.json_response(
            {
                "values": config.raw,
                "settings_path": str(config.settings_path) if config.settings_path else None,
                "personalities": list(PRESETS),
                "agents": list(config.agents),
                "skills": sorted(plugins.available("dia.skills")),
                "tts": sorted(plugins.available("dia.tts")),
                "agent_types": sorted(plugins.available("dia.agents")),
                "agent_models": sorted(
                    {m for kind in plugins.available("dia.agents") for m in _models_of(kind)}
                ),
                # what the forms set (removable there), apart from the config file
                "overlay": read_settings(config.source) if config.source else {},
            }
        )

    async def apply_suggestion(self, request: web.Request) -> web.Response:
        """Make the proposed agent a project's default (the only thing a proposal changes)."""
        from dia.quality.agent_stats import agent_stats, suggestions

        body = await request.json()
        allowed = suggestions(self.dia.config, agent_stats(self.dia.store, 90))
        match = next(
            (s for s in allowed if (s["project"], s["agent"]) == (body["project"], body["agent"])),
            None,
        )
        if not match:
            raise ValueError("no such proposal")
        new = save_settings(
            self.dia.config, {"projects": {match["project"]: {"default_agent": match["agent"]}}}
        )
        self.dia.apply_config(new)
        self.dia.audit(
            "agents.default", match["project"], f"{match['current']} -> {match['agent']}"
        )
        return web.json_response({"message": f"{match['project']}: {match['agent']}"})

    async def put_settings(self, request: web.Request) -> web.Response:
        """Save form changes to settings.json and use them at once where possible."""
        changes = (await request.json()).get("changes", {})
        if not isinstance(changes, dict):
            raise ValueError("changes must be an object")
        new = save_settings(self.dia.config, changes)
        self.dia.apply_config(new)
        self.dia.audit("settings.change", None, ", ".join(sorted(changes)))
        restart = sorted(k for k in changes if k in RESTART_SECTIONS)
        return web.json_response({"saved": True, "restart_required": restart})

    async def list_secrets(self, request: web.Request) -> web.Response:
        from dia import secrets as secret_store

        return web.json_response(secret_store.status())

    async def set_secret(self, request: web.Request) -> web.Response:
        from dia import secrets as secret_store

        value = (await request.json()).get("value", "")
        secret_store.set_secret(request.match_info["name"], value)
        self.dia.audit("secret.set", request.match_info["name"])
        return web.json_response({"message": "saved"})

    async def remove_secret(self, request: web.Request) -> web.Response:
        from dia import secrets as secret_store

        secret_store.remove_secret(request.match_info["name"])
        self.dia.audit("secret.remove", request.match_info["name"])
        return web.json_response({"message": "removed"})

    async def push_info(self, request: web.Request) -> web.Response:
        if not push_available():
            return web.json_response({"available": False})
        device = request[DEVICE].name if request[DEVICE] else None
        mine = [
            s for s in self.push.subscriptions() if s.get("device") == (device or "this computer")
        ]
        return web.json_response(
            {"available": True, "key": self.push.public_key(), "subscriptions": len(mine)}
        )

    async def push_subscribe(self, request: web.Request) -> web.Response:
        device = request[DEVICE].name if request[DEVICE] else None
        self.push.subscribe(await request.json(), device)
        return web.json_response({"message": "subscribed"}, status=201)

    async def push_unsubscribe(self, request: web.Request) -> web.Response:
        endpoint = (await request.json()).get("endpoint", "")
        return web.json_response({"removed": self.push.unsubscribe(endpoint)})

    async def push_test(self, request: web.Request) -> web.Response:
        sent = await self.push.send("Dia", "🔔 Test", "/", tag="test")
        return web.json_response({"message": f"sent to {sent} device(s)"})

    async def get_config(self, request: web.Request) -> web.Response:
        source = self.dia.config.source
        return web.json_response(
            {
                "path": str(source) if source else None,
                "text": source.read_text() if source and source.exists() else "",
                "shadowed": [str(p) for p in self.dia.config.shadowed],
            }
        )

    async def put_config(self, request: web.Request) -> web.Response:
        """Validate and save the config file (the old one is kept as .bak)."""
        source = self.dia.config.source
        if not source:
            raise ConfigError("Dia was started without a config file")
        text = (await request.json())["text"]
        try:
            parse_config(tomllib.loads(text), source)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"invalid TOML: {exc}") from None
        if source.exists():
            source.with_suffix(source.suffix + ".bak").write_text(source.read_text())
        source.write_text(text)
        self.dia.audit("config.save", str(source))
        return web.json_response({"saved": str(source), "restart_required": True})

    async def themes(self, request: web.Request) -> web.Response:
        built_in = sorted(p.stem for p in (STATIC / "themes").glob("*.css"))
        user_dir = user_themes_dir()
        custom = sorted(p.stem for p in user_dir.glob("*.css")) if user_dir.is_dir() else []
        return web.json_response({"built_in": built_in, "custom": custom, "dir": str(user_dir)})

    async def get_theme(self, request: web.Request) -> web.Response:
        from dia.ui import theme

        data_dir = self.dia.config.data_dir
        mine = theme.current(data_dir, "phone" if request[DEVICE] else None)
        return web.json_response(
            {**theme.settings(data_dir), "effective": mine, "colors": theme.colors(mine)}
        )

    async def put_theme(self, request: web.Request) -> web.Response:
        """The app's theme, and the phone's and the widget's (their own, or None: the app's).
        Every open page switches at once. A paired phone sets only its own."""
        from dia.ui import theme

        body = await request.json()
        changes = dict(body) if isinstance(body, dict) else {}
        device = request[DEVICE]
        if device and not device.full and set(changes) - {"phone"}:
            return web.json_response({"error": "a phone sets only its own theme"}, status=403)
        try:
            chosen = theme.update(self.dia.config.data_dir, changes)
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        await self._broadcast({"type": "theme", **chosen})
        mine = theme.current(self.dia.config.data_dir, "phone" if device else None)
        return web.json_response({**chosen, "effective": mine, "colors": theme.colors(mine)})

    async def theme_css(self, request: web.Request) -> web.FileResponse:
        name = request.match_info["name"]
        for folder in (user_themes_dir(), STATIC / "themes"):
            path = folder / f"{name}.css"
            if path.is_file() and path.resolve().parent == folder.resolve():
                return web.FileResponse(path, headers={"Content-Type": "text/css"})
        raise web.HTTPNotFound(text="no such theme")


def routes(ch: SettingsRoutes) -> list[web.RouteDef]:
    return [
        web.get("/api/config", ch.get_config),
        web.put("/api/config", ch.put_config),
        web.get("/api/themes", ch.themes),
        web.get("/themes/{name}.css", ch.theme_css),
        web.get("/api/theme", ch.get_theme),
        web.put("/api/theme", ch.put_theme),
        web.get("/api/devices", ch.list_devices),
        web.post("/api/devices", ch.pair_device),
        web.delete("/api/devices/{id}", ch.revoke_device),
        web.patch("/api/devices/{id}", ch.update_device),
        web.post("/api/settings/apply-suggestion", ch.apply_suggestion),
        web.get("/api/settings", ch.get_settings),
        web.put("/api/settings", ch.put_settings),
        web.get("/api/secrets", ch.list_secrets),
        web.put("/api/secrets/{name}", ch.set_secret),
        web.delete("/api/secrets/{name}", ch.remove_secret),
        web.get("/api/push", ch.push_info),
        web.post("/api/push/subscribe", ch.push_subscribe),
        web.post("/api/push/unsubscribe", ch.push_unsubscribe),
        web.post("/api/push/test", ch.push_test),
    ]
