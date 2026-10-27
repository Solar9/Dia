"""Built-in skills: weather, news, markets, and the daily briefing.

All of them work without API keys:

- weather: Open-Meteo (geocoding + forecast);
- news: any RSS / Atom feeds you list;
- stocks: Yahoo Finance chart data (``source = "stooq"`` for Stooq instead);
- crypto: CoinGecko's public prices.
"""

from __future__ import annotations

import asyncio
import csv
import io
import re
import tempfile
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from html import unescape
from pathlib import Path
from typing import Any

from dia.persona import greeting
from dia.skills import Skill, fetch, fetch_json

# WMO weather codes (Open-Meteo), grouped.
_WMO = [
    ({0}, "bezchmurnie", "clear sky"),
    ({1, 2}, "lekkie zachmurzenie", "partly cloudy"),
    ({3}, "pochmurno", "overcast"),
    ({45, 48}, "mgła", "fog"),
    ({51, 53, 55, 56, 57}, "mżawka", "drizzle"),
    ({61, 63, 65, 66, 67, 80, 81, 82}, "deszcz", "rain"),
    ({71, 73, 75, 77, 85, 86}, "śnieg", "snow"),
    ({95, 96, 99}, "burza", "thunderstorm"),
]


def describe_weather(code: int | None, language: str) -> str:
    for codes, pl, en in _WMO:
        if code in codes:
            return pl if language == "pl" else en
    return "?"


# Polish place names come inflected ("w Krakowie", "w Gdańsku", "w Poznaniu");
# the geocoder knows the base form. (ending, replacement), tried in order.
_LOCATIVE = [
    ("owie", "ów"),
    ("niu", "ń"),
    ("dzie", "d"),
    ("rze", "r"),
    ("rze", "ra"),
    ("cie", "ta"),
    ("ie", "a"),
    ("ie", ""),
    ("u", ""),
    ("y", "a"),
    ("i", "a"),
    ("e", "a"),
]


def place_candidates(place: str) -> list[str]:
    """The name as given, then guesses at its base form (Krakowie → Kraków)."""
    words = place.split()
    candidates = [place]
    for ending, base in _LOCATIVE:
        last = words[-1]
        if last.lower().endswith(ending) and len(last) > len(ending) + 1:
            # Adjectives before the noun: "Zielonej Górze" -> "Zielona Góra".
            head = [w[:-2] + "a" if w.lower().endswith("ej") else w for w in words[:-1]]
            guess = " ".join([*head, last[: -len(ending)] + base])
            if guess not in candidates:
                candidates.append(guess)
    return candidates


class WeatherSkill(Skill):
    """``[skills.weather] place = "Kraków"`` (or ``latitude``/``longitude``)."""

    kind = "weather"
    description = "current weather and today's/tomorrow's forecast"
    args = {"place": "city name, optional (default: the configured one)", "day": "today|tomorrow"}

    async def locate(self, place: str | None) -> tuple[float, float, str]:
        if not place and "latitude" in self.options:
            return (
                float(self.options["latitude"]),
                float(self.options["longitude"]),
                self.options.get("place", ""),
            )
        place = place or self.options.get("place")
        if not place:
            raise ValueError(
                self.t(
                    "Nie wiem, dla jakiego miejsca: ustaw miasto w Ustawieniach → Asystent.",
                    "Which place? Set a city in Settings → Assistant.",
                )
            )
        for name in place_candidates(place):
            data = await fetch_json(
                "https://geocoding-api.open-meteo.com/v1/search",
                {"name": name, "count": 1, "language": self.language},
            )
            if data.get("results"):
                hit = data["results"][0]
                return hit["latitude"], hit["longitude"], hit.get("name", name)
        raise ValueError(self.t(f"Nie znam miejsca „{place}”.", f"I can't find “{place}”."))

    async def run(self, args: dict[str, Any]) -> str:
        try:
            lat, lon, name = await self.locate(args.get("place"))
        except ValueError as exc:
            return str(exc)
        data = await fetch_json(
            "https://api.open-meteo.com/v1/forecast",
            {
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
                "daily": "temperature_2m_max,temperature_2m_min,"
                "precipitation_probability_max,weather_code",
                "timezone": "auto",
                "forecast_days": 2,
            },
        )
        return self.render(data, name, args.get("day") == "tomorrow")

    def render(self, data: dict[str, Any], name: str, tomorrow: bool) -> str:
        daily = data["daily"]
        i = 1 if tomorrow else 0
        sky = describe_weather(daily["weather_code"][i], self.language)
        high, low = round(daily["temperature_2m_max"][i]), round(daily["temperature_2m_min"][i])
        rain = daily.get("precipitation_probability_max", [None, None])[i]
        where = f" ({name})" if name else ""
        if tomorrow:
            text = self.t(
                f"Jutro{where}: {sky}, od {low} do {high}°C",
                f"Tomorrow{where}: {sky}, {low} to {high}°C",
            )
        else:
            now = data["current"]
            temp, feels = round(now["temperature_2m"]), round(now["apparent_temperature"])
            current = describe_weather(now["weather_code"], self.language)
            text = self.t(
                f"Teraz{where} {temp}°C (odczuwalnie {feels}), {current}. "
                f"Dziś od {low} do {high}°C, {sky}",
                f"Now{where} {temp}°C (feels like {feels}), {current}. "
                f"Today {low} to {high}°C, {sky}",
            )
        if rain is not None:
            text += self.t(f", szansa opadów {rain}%.", f", {rain}% chance of rain.")
        return text


DEFAULT_FEEDS = {
    "pl": ["https://tvn24.pl/najnowsze.xml", "https://www.rmf24.pl/fakty/feed"],
    "en": ["https://feeds.bbci.co.uk/news/rss.xml"],
}


def parse_feed(data: bytes) -> list[dict[str, str]]:
    """Items of an RSS or Atom feed: title, link, published (as given)."""
    root = ET.fromstring(data)
    items = []
    for node in root.iter():
        tag = node.tag.rsplit("}", 1)[-1]
        if tag not in ("item", "entry"):
            continue
        fields: dict[str, str] = {}
        for child in node:
            name = child.tag.rsplit("}", 1)[-1]
            if name == "title":
                fields["title"] = unescape(re.sub(r"<[^>]+>", "", child.text or "")).strip()
            elif name == "link":
                fields["link"] = (child.text or child.get("href") or "").strip()
            elif name in ("pubDate", "published", "updated"):
                fields.setdefault("published", (child.text or "").strip())
        if fields.get("title"):
            items.append(fields)
    return items


class NewsSkill(Skill):
    """``[skills.news] feeds = ["https://...rss"]``, ``count = 5``."""

    kind = "news"
    description = "latest headlines from the user's news feeds"
    args = {"topic": "optional word to filter headlines by"}

    async def headlines(self, topic: str | None = None) -> list[dict[str, str]]:
        feeds = self.options.get("feeds") or DEFAULT_FEEDS.get(self.language, DEFAULT_FEEDS["en"])
        results = await asyncio.gather(*(fetch(url) for url in feeds), return_exceptions=True)
        per_feed = []
        for result in results:
            if isinstance(result, BaseException):
                continue
            try:
                per_feed.append(parse_feed(result))
            except ET.ParseError:
                continue
        # Interleave the feeds so one source doesn't take every slot.
        items, seen = [], set()
        for row in range(max((len(f) for f in per_feed), default=0)):
            for feed in per_feed:
                if row < len(feed) and feed[row]["title"].lower() not in seen:
                    seen.add(feed[row]["title"].lower())
                    items.append(feed[row])
        if topic:
            items = [i for i in items if topic.lower() in i["title"].lower()]
        return items

    async def run(self, args: dict[str, Any]) -> str:
        count = int(self.options.get("count", 5))
        items = (await self.headlines(args.get("topic")))[:count]
        if not items:
            return self.t("Nie udało się pobrać wiadomości.", "I couldn't get any news.")
        lines = "\n".join(f"- {i['title']}" for i in items)
        return self.t("Najważniejsze wiadomości:\n", "Top headlines:\n") + lines


class StocksSkill(Skill):
    """``[skills.stocks] symbols = ["AAPL", "CDR.WA", "^GSPC"]`` (Yahoo symbols), or
    ``source = "stooq"`` with Stooq symbols (``aapl.us``, ``cdr``, ``wig20``)."""

    kind = "stocks"
    description = "prices and daily change of stocks, indices or currencies"
    args = {"symbols": "list of ticker symbols, optional (default: the watchlist)"}

    async def quote(self, symbol: str) -> tuple[float, float | None, str]:
        """(price, change in % since the previous close, currency)."""
        if self.options.get("source") == "stooq":
            start = (datetime.now(UTC) - timedelta(days=14)).strftime("%Y%m%d")
            text = (
                await fetch(
                    "https://stooq.com/q/d/l/", {"s": symbol.lower(), "i": "d", "d1": start}
                )
            ).decode()
            rows = [r for r in csv.DictReader(io.StringIO(text)) if r.get("Close")]
            if not rows:
                raise ValueError(symbol)
            close = float(rows[-1]["Close"])
            prev = float(rows[-2]["Close"]) if len(rows) > 1 else None
            return close, (close / prev - 1) * 100 if prev else None, ""
        data = await fetch_json(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
            {"range": "5d", "interval": "1d"},
        )
        meta = data["chart"]["result"][0]["meta"]
        price = float(meta["regularMarketPrice"])
        prev = meta.get("chartPreviousClose") or meta.get("previousClose")
        change = (price / float(prev) - 1) * 100 if prev else None
        return price, change, meta.get("currency", "")

    async def run(self, args: dict[str, Any]) -> str:
        symbols = args.get("symbols") or self.options.get("symbols") or []
        if isinstance(symbols, str):
            symbols = [s for s in re.split(r"[,\s]+", symbols) if s]
        if not symbols:
            return self.t(
                "Nie masz listy notowań: dodaj symbole w Ustawieniach → Asystent.",
                "No watchlist yet: add symbols in Settings → Assistant.",
            )
        results = await asyncio.gather(*(self.quote(s) for s in symbols), return_exceptions=True)
        lines = []
        for symbol, result in zip(symbols, results, strict=True):
            if isinstance(result, BaseException):
                lines.append(f"- {symbol}: " + self.t("brak danych", "no data"))
                continue
            price, change, currency = result
            delta = f" ({change:+.2f}%)" if change is not None else ""
            lines.append(f"- {symbol}: {price:,.2f} {currency}{delta}".replace("  ", " "))
        return "\n".join(lines)


# Common tickers -> CoinGecko ids (anything else: write the CoinGecko id itself).
COINS = {
    "btc": "bitcoin", "eth": "ethereum", "sol": "solana", "bnb": "binancecoin",
    "xrp": "ripple", "ada": "cardano", "doge": "dogecoin", "dot": "polkadot",
    "ltc": "litecoin", "avax": "avalanche-2", "link": "chainlink", "trx": "tron",
    "xmr": "monero", "usdt": "tether", "usdc": "usd-coin", "ton": "the-open-network",
    "matic": "matic-network", "pol": "matic-network", "atom": "cosmos", "xlm": "stellar",
}  # fmt: skip


class CryptoSkill(Skill):
    """``[skills.crypto] coins = ["btc", "eth", "sol"]``, ``currency = "pln"``
    (default: usd). Tickers or CoinGecko ids; prices with the 24 h change."""

    kind = "crypto"
    description = "cryptocurrency prices and their 24 h change (bitcoin, ethereum, ...)"
    args = {
        "coins": "list of coins (btc, eth, or CoinGecko ids), optional (default: the watchlist)",
        "currency": "currency to price in (usd, pln, eur), optional",
    }

    async def run(self, args: dict[str, Any]) -> str:
        coins = args.get("coins") or self.options.get("coins") or ["btc", "eth"]
        if isinstance(coins, str):
            coins = [c for c in re.split(r"[,\s]+", coins) if c]
        currency = str(args.get("currency") or self.options.get("currency") or "usd").lower()
        ids = [COINS.get(c.lower(), c.lower()) for c in coins]
        data = await fetch_json(
            "https://api.coingecko.com/api/v3/simple/price",
            {
                "ids": ",".join(dict.fromkeys(ids)),
                "vs_currencies": currency,
                "include_24hr_change": "true",
            },
        )
        lines = []
        for coin, coin_id in zip(coins, ids, strict=True):
            entry = data.get(coin_id) or {}
            price = entry.get(currency)
            if price is None:
                lines.append(f"- {coin.upper()}: " + self.t("brak danych", "no data"))
                continue
            change = entry.get(f"{currency}_24h_change")
            delta = f" ({change:+.2f}% 24h)" if change is not None else ""
            digits = 2 if price >= 1 else 6
            lines.append(f"- {coin.upper()}: {price:,.{digits}f} {currency.upper()}{delta}")
        return "\n".join(lines)


class BriefingSkill(Skill):
    """The daily briefing: weather, your agents' work, news and markets.

    ``[skills.briefing] sections = ["weather", "work", "news", "stocks"]``
    """

    kind = "briefing"
    description = "a short daily briefing: weather, what the agents did, news, markets"

    def work(self) -> str:
        since = datetime.now(UTC) - timedelta(hours=float(self.options.get("hours", 24)))
        recent = [
            t
            for t in self.dia.store.recent(200)
            if datetime.fromisoformat(t.created_at) >= since and t.mode != "check"
        ]
        done = [t for t in recent if t.status in ("done", "merged", "published")]
        failed = [t for t in recent if t.status == "failed"]
        waiting = [t for t in recent if t.status == "done" and t.commit_sha]
        broken = [t for t in self.dia.store.recent(50) if t.mode == "check"][:1]
        parts = [
            self.t(
                f"Od wczoraj: {len(done)} zadań gotowych, {len(failed)} nieudanych",
                f"Since yesterday: {len(done)} tasks done, {len(failed)} failed",
            )
        ]
        if waiting:
            parts.append(
                self.t(
                    f"{len(waiting)} czeka na Twoją decyzję (scal / odrzuć)",
                    f"{len(waiting)} waiting for your decision (merge / discard)",
                )
            )
        if broken and broken[0].tests_ok is False:
            parts.append(
                self.t(
                    f"testy w {broken[0].project} nie przechodzą",
                    f"the tests in {broken[0].project} are failing",
                )
            )
        if facts := len(self.dia.pending_facts()):
            parts.append(self.t(f"{facts} propozycji do pamięci", f"{facts} facts to review"))
        return ", ".join(parts) + "."

    async def run(self, args: dict[str, Any]) -> str:
        from dia.skills import enabled_skills

        default = ["weather", "calendar", "mail", "work", "news", "stocks", "crypto"]
        sections = self.options.get("sections", default)
        skills = enabled_skills(self.dia)
        out = [greeting(self.config, datetime.now().hour) + "."]
        for section in sections:
            try:
                if section == "work":
                    out.append(self.work())
                elif section in skills and section != self.kind:
                    skill = skills[section]
                    if section in ("stocks", "crypto") and not (
                        skill.options.get("symbols") or skill.options.get("coins")
                    ):
                        continue
                    if section == "calendar" and not skill.urls():
                        continue
                    if section == "mail" and not skill.options.get("host"):
                        continue
                    out.append(await skill.run({}))
            except Exception as exc:  # one broken source doesn't spoil the briefing
                out.append(f"({section}: {exc})")
        return "\n\n".join(out)


class SystemSkill(Skill):
    """How the computer is doing: CPU, temperature, memory, disks, battery, and
    (``top``) what uses the most."""

    kind = "system"
    description = "this computer's state: CPU, temperature, RAM, disks, battery, top processes"
    args = {"top": "true to list what uses the most CPU/memory"}

    async def run(self, args: dict[str, Any]) -> str:
        from dia import system

        snap = await system.snapshot()
        temp = f", {snap.cpu_temp:.0f}°C" if snap.cpu_temp is not None else ""
        mem = snap.memory
        parts = [
            self.t(
                f"Procesor {snap.cpu_percent:.0f}%{temp}. Pamięć {mem['used_gb']} z "
                f"{mem['total_gb']} GB ({mem['percent']:.0f}%).",
                f"CPU {snap.cpu_percent:.0f}%{temp}. Memory {mem['used_gb']} of "
                f"{mem['total_gb']} GB ({mem['percent']:.0f}%).",
            )
        ]
        for disk in snap.disks[:3]:
            free, used = disk["total_gb"] - disk["used_gb"], disk["percent"]
            parts.append(
                self.t(
                    f"Dysk {disk['mount']}: wolne {free:.0f} GB ({used:.0f}% zajęte).",
                    f"Disk {disk['mount']}: {free:.0f} GB free ({used:.0f}% used).",
                )
            )
        if bat := snap.battery:
            states = {
                "Charging": self.t("ładuje się", "charging"),
                "Discharging": self.t("na baterii", "on battery"),
            }
            state = states.get(bat["status"], bat["status"])
            parts.append(
                self.t(
                    f"Bateria {bat['percent']}% ({state}).", f"Battery {bat['percent']}% ({state})."
                )
            )
        if str(args.get("top", "")).lower() in ("true", "1", "yes"):
            top = await system.processes(5)
            listing = ", ".join(
                f"{p.name} {p.cpu_percent:.0f}% CPU / {p.memory_mb:.0f} MB" for p in top
            )
            parts.append(self.t("Najwięcej zużywa: ", "Using the most: ") + listing + ".")
        return " ".join(parts)


class ScreenSkill(Skill):
    """Look at the screen and answer a question about it (only when switched on)."""

    kind = "screen"
    description = (
        "look at the user's screen and answer about it (errors, code, what is open); "
        "works only while screen access is on"
    )
    args = {"question": "what the user wants to know about the screen"}

    async def run(self, args: dict[str, Any]) -> str:
        from dia.screen import look

        if not self.dia.screen_enabled:
            return self.t(
                "Nie widzę ekranu: dostęp jest wyłączony. Włącz go przełącznikiem 👁 "
                "w aplikacji albo powiedz „możesz patrzeć na ekran”.",
                "I can't see the screen: access is off. Switch it on with the 👁 switch "
                "in the app or say “you can look at the screen”.",
            )
        return await look(self.dia, str(args.get("question") or ""))


class BalanceSkill(Skill):
    """Game balance from playtest data: levels, causes of death, weapons."""

    kind = "balance"
    description = (
        "a game's balance from playtest data: win rates and times per level, what kills "
        "players, which weapons do the damage; advise=true for proposed changes"
    )
    args = {"project": "which game", "advise": "true for an agent's proposed changes"}

    async def run(self, args: dict[str, Any]) -> str:
        from dia.balance import balance_report

        project = str(args.get("project") or "")
        if not project and len(self.config.projects) == 1:
            project = next(iter(self.config.projects))
        if not project:
            return self.t("Którego projektu?", "Which project?")
        advise = str(args.get("advise", "")).lower() in ("true", "1", "yes")
        return await balance_report(self.dia, project, advise)


class AnalyzeSkill(Skill):
    """Scenes, scripts and textures of a Godot project, checked for likely problems."""

    kind = "analyze"
    description = (
        "analyse a Godot project's scenes, scripts and textures for performance and "
        "structure problems; advise=true lets an agent read the code and prioritise"
    )
    args = {"project": "which project", "advise": "true for an agent's advice"}

    async def run(self, args: dict[str, Any]) -> str:
        from dia.godot_analysis import analyze_project

        project = str(args.get("project") or "")
        if not project and len(self.config.projects) == 1:
            project = next(iter(self.config.projects))
        if not project:
            return self.t("Którego projektu?", "Which project?")
        advise = str(args.get("advise", "")).lower() in ("true", "1", "yes")
        return await analyze_project(self.dia, project, advise)


class ClipboardSkill(Skill):
    """Read the clipboard, put text into it, or change what is in it."""

    kind = "clipboard"
    description = (
        "the user's clipboard: say what is in it (read), put text into it (copy), or "
        "change its text and put the result back (transform: translate, fix, shorten...)"
    )
    args = {
        "action": "read|copy|transform",
        "text": "copy: the text to put in the clipboard",
        "instruction": "transform: what to do with the text, e.g. 'translate to English'",
    }

    async def run(self, args: dict[str, Any]) -> str:
        from dia import clipboard
        from dia.agents import AgentRequest, Mode

        action = str(args.get("action") or "read").lower()
        reader, writer = self.options.get("read_command"), self.options.get("write_command")
        if action == "copy":
            text = str(args.get("text") or "")
            await clipboard.write(text, writer)
            return self.t("Skopiowane do schowka.", "Copied to the clipboard.")
        content = await clipboard.read(reader)
        self.dia.audit("clipboard.read", None, action)
        if not content.strip():
            return self.t("Schowek jest pusty.", "The clipboard is empty.")
        if action != "transform":
            limit = int(self.options.get("max_chars", 1500))
            return content[:limit] + ("…" if len(content) > limit else "")
        instruction = str(args.get("instruction") or "fix spelling and grammar")
        agent = self.config.agent(self.options.get("agent"))
        with tempfile.TemporaryDirectory(prefix="dia-clipboard-") as empty:
            _, result = await self.dia.call_agent(
                agent,
                AgentRequest(
                    prompt=(
                        f"{instruction}\n\nAnswer with the resulting text only, nothing "
                        f"before or after it.\n\n<text>\n{content[:20000]}\n</text>"
                    ),
                    cwd=Path(empty),
                    mode=Mode.READ_ONLY,
                    model=self.options.get("model"),
                    tools=False,
                ),
                purpose="clipboard",
            )
        if not result.success or not result.summary.strip():
            return self.t(f"Nie udało się: {result.error}", f"That didn't work: {result.error}")
        await clipboard.write(result.summary.strip(), writer)
        return (
            self.t("Gotowe, wynik jest w schowku:\n", "Done, it's in the clipboard:\n")
            + (result.summary.strip()[:600])
        )


class TidySkill(Skill):
    """Tidy Downloads (or another allowed folder): a preview first, then your yes."""

    kind = "tidy"
    description = (
        "tidy the Downloads folder: sort files into folders by type and archive old "
        "ones (shows what would move and asks first; can undo)"
    )
    args = {"folder": "which allowed folder (default: Downloads)", "undo": "true to undo"}

    async def run(self, args: dict[str, Any]) -> str:
        from dia.skills import NeedsConfirmation
        from dia.tidy import Tidy, files_pl, summary

        tidy = Tidy(self.dia)
        if str(args.get("undo", "")).lower() in ("true", "1", "yes"):
            plan = tidy.undo()
            return self.t(
                f"Cofnięte, wróciło na miejsce: {files_pl(plan['restored'])}.",
                f"Undone: {plan['restored']} files are back.",
            )
        plan = tidy.plan(args.get("folder") or None)
        text = summary(plan, self.language)
        if not plan["moves"]:
            return text

        async def apply() -> str:
            done = tidy.apply(plan["id"])
            return self.t(
                f"Gotowe, przeniesione: {files_pl(len(done['moved']))}. „Cofnij porządki” odwraca.",
                f"Done: moved {len(done['moved'])}. Say “undo tidying” to put them back.",
            )

        raise NeedsConfirmation(text + self.t(" Przenieść?", " Go ahead?"), apply)


class CameraSkill(Skill):
    """One photo from the camera, answered by an agent (only when switched on)."""

    kind = "camera"
    description = (
        "take one photo with the user's camera and answer about it (what they hold up, "
        "how they look on a call); works only while camera access is on"
    )
    args = {"question": "what the user wants to know about what the camera sees"}

    async def run(self, args: dict[str, Any]) -> str:
        from dia.camera import look

        if not self.dia.camera_enabled:
            return self.t(
                "Kamera jest wyłączona. Włącz ją przełącznikiem 📷 w aplikacji "
                "albo powiedz „włącz kamerę”.",
                "The camera is off. Switch it on with the 📷 switch in the app "
                "or say “camera access on”.",
            )
        return await look(self.dia, str(args.get("question") or ""))


class ServicesSkill(Skill):
    """Failed systemd units (system and user) and broken containers."""

    kind = "services"
    description = "failed systemd services and Docker/Podman containers that are down"

    async def run(self, args: dict[str, Any]) -> str:
        from dia import computer

        units, boxes = await asyncio.gather(computer.failed_units(), computer.containers())
        if not units and not boxes:
            return self.t("Wszystkie usługi działają.", "All services are running.")
        lines = [f"- {u['unit']} ({u['scope']})" for u in units]
        lines += [f"- {c['tool']} {c['name']}: {c['status']}" for c in boxes]
        return self.t("Nie działa:\n", "Not running:\n") + "\n".join(lines)


class UpdatesSkill(Skill):
    """Pending package updates (pacman/AUR/flatpak, or apt/dnf). Never installs."""

    kind = "updates"
    description = "pending system updates (pacman, AUR, flatpak...); reports only"

    async def run(self, args: dict[str, Any]) -> str:
        from dia import computer

        found = [u for u in await computer.updates() if u.packages]
        if not found:
            return self.t("Wszystko aktualne.", "Everything is up to date.")
        lines = []
        for u in found:
            names = ", ".join(u.packages[:8]) + (" …" if len(u.packages) > 8 else "")
            lines.append(f"- {u.source}: {len(u.packages)} ({names}) → {u.command}")
        return self.t("Dostępne aktualizacje:\n", "Updates available:\n") + "\n".join(lines)


class SecuritySkill(Skill):
    """A security report of this computer, its network and your projects."""

    kind = "security"
    description = (
        "security report: ports open to the network, firewall, failed logins, "
        "devices on the network, vulnerable project dependencies"
    )
    args = {"scan": "optional: one of YOUR hosts to port-scan"}

    async def run(self, args: dict[str, Any]) -> str:
        from dia import security

        options = self.config.section("security")
        if host := args.get("scan"):
            try:
                ports = await security.scan(str(host), options)
            except security.NotAuthorized as exc:
                return str(exc)
            listing = ", ".join(f"{p['port']} {p['service']}".strip() for p in ports) or "-"
            return self.t(f"Otwarte porty na {host}: {listing}", f"Open ports on {host}: {listing}")
        rep = await security.report(self.dia)
        return security.describe(rep, self.language)
