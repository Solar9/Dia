"""Skills that read your calendar and mail, and control your home.

- calendar: any iCal (.ics) address, e.g. Google Calendar's "secret address in
  iCal format", kept as the secret DIA_CALENDAR_URL. Read-only.
- mail: IMAP, read-only (unread messages); the password (for Gmail an app
  password) is the secret DIA_MAIL_PASSWORD. Dia never sends or deletes mail.
- home: Home Assistant's REST API with a long-lived token (secret HA_TOKEN).
  Locks, alarms, covers and garage doors ask for a yes first.
"""

from __future__ import annotations

import asyncio
import email.header
import email.utils
import imaplib
import json
import logging
import os
import re
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from typing import Any
from zoneinfo import ZoneInfo

from dia.skills import NeedsConfirmation, Skill, fetch

log = logging.getLogger("dia.skills.integrations")

# --------------------------------------------------------------- calendar ---


def _unfold(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        if raw.startswith((" ", "\t")) and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def _parse_time(value: str, params: dict[str, str], local: Any) -> datetime | date:
    if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", value):
        return datetime.strptime(value[:8], "%Y%m%d").date()
    moment = datetime.strptime(value.rstrip("Z")[:15], "%Y%m%dT%H%M%S")
    if value.endswith("Z"):
        return moment.replace(tzinfo=ZoneInfo("UTC")).astimezone(local)
    try:
        zone = ZoneInfo(params["TZID"]) if "TZID" in params else local
    except Exception:
        zone = local
    return moment.replace(tzinfo=zone).astimezone(local)


def parse_ics(text: str, local: Any = None) -> list[dict[str, Any]]:
    """VEVENTs: summary, location, start, end, rrule (start/end are dates or datetimes)."""
    local = local or datetime.now().astimezone().tzinfo
    events, current = [], None
    for line in _unfold(text):
        if line == "BEGIN:VEVENT":
            current = {}
        elif line == "END:VEVENT" and current is not None:
            if "start" in current:
                events.append(current)
            current = None
        elif current is not None and ":" in line:
            head, value = line.split(":", 1)
            name, *rest = head.split(";")
            params = dict(p.split("=", 1) for p in rest if "=" in p)
            if name == "SUMMARY":
                current["summary"] = value.replace("\\,", ",").replace("\\n", " ")
            elif name == "LOCATION":
                current["location"] = value.replace("\\,", ",")
            elif name in ("DTSTART", "DTEND"):
                current["start" if name == "DTSTART" else "end"] = _parse_time(value, params, local)
            elif name == "RRULE":
                current["rrule"] = dict(p.split("=", 1) for p in value.split(";") if "=" in p)
            elif name == "EXDATE":
                current.setdefault("exdates", []).extend(
                    _parse_time(v, params, local) for v in value.split(",")
                )
    return events


_DAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]


def occurs_on(event: dict[str, Any], day: date) -> datetime | date | None:
    """The event's start on ``day`` (recurring daily/weekly/monthly/yearly), else None."""
    start = event["start"]
    first = start.date() if isinstance(start, datetime) else start
    at = (
        (lambda d: datetime.combine(d, start.timetz()))
        if isinstance(start, datetime)
        else (lambda d: d)
    )
    if first == day:
        return start
    rule = event.get("rrule")
    if not rule or day < first:
        return None
    if until := rule.get("UNTIL"):
        if day > datetime.strptime(until[:8], "%Y%m%d").date():
            return None
    excluded = {e.date() if isinstance(e, datetime) else e for e in event.get("exdates", [])}
    if day in excluded:
        return None
    interval = int(rule.get("INTERVAL", 1))
    freq = rule.get("FREQ")
    delta = (day - first).days
    if freq == "DAILY":
        hit = delta % interval == 0
    elif freq == "WEEKLY":
        days = rule.get("BYDAY", _DAYS[first.weekday()]).split(",")
        hit = _DAYS[day.weekday()] in [d[-2:] for d in days] and (delta // 7) % interval == 0
    elif freq == "MONTHLY":
        months = (day.year - first.year) * 12 + day.month - first.month
        hit = day.day == first.day and months % interval == 0
    elif freq == "YEARLY":
        hit = (day.month, day.day) == (first.month, first.day)
    else:
        hit = False
    if hit and (count := rule.get("COUNT")):
        hit = delta < int(count) * {"DAILY": 1, "WEEKLY": 7}.get(freq, 31) * interval
    return at(day) if hit else None


class CalendarSkill(Skill):
    kind = "calendar"
    description = "the user's calendar: events today, tomorrow or on a date"
    args = {"day": "today|tomorrow|YYYY-MM-DD"}

    def urls(self) -> list[str]:
        names = self.options.get("url_secrets", ["DIA_CALENDAR_URL"])
        return [os.environ[n] for n in names if os.environ.get(n)]

    async def events(self, day: date) -> tuple[list[tuple[Any, dict[str, Any]]], int]:
        """The day's events, and how many calendars could not be read."""
        found, failed = [], 0
        for url in self.urls():
            try:
                text = (await fetch(url)).decode(errors="replace")
            except (OSError, ValueError) as exc:
                log.warning("calendar unavailable: %s", exc)
                failed += 1
                continue
            for event in parse_ics(text):
                if (at := occurs_on(event, day)) is not None:
                    found.append((at, event))
        found.sort(key=lambda e: (isinstance(e[0], datetime), str(e[0])))
        return found, failed

    async def run(self, args: dict[str, Any]) -> str:
        if not self.urls():
            return self.t(
                "Nie znam Twojego kalendarza: dodaj jego adres iCal jako sekret DIA_CALENDAR_URL.",
                "I don't know your calendar: add its iCal address as the secret DIA_CALENDAR_URL.",
            )
        wanted = str(args.get("day") or "today")
        today = date.today()
        day = {"today": today, "tomorrow": today + timedelta(days=1)}.get(wanted)
        if day is None:
            try:
                day = date.fromisoformat(wanted)
            except ValueError:
                day = today
        events, failed = await self.events(day)
        if failed == len(self.urls()):
            return self.t(
                "Nie mogę teraz odczytać kalendarza (brak połączenia z serwerem kalendarza).",
                "I can't read the calendar right now (its server didn't answer).",
            )
        label = self.t(
            "Dziś" if day == today else "Jutro" if day == today + timedelta(1) else str(day),
            "Today" if day == today else "Tomorrow" if day == today + timedelta(1) else str(day),
        )
        note = (
            self.t(
                f" (nie udało się odczytać kalendarzy: {failed})",
                f" ({failed} calendar(s) could not be read)",
            )
            if failed
            else ""
        )
        if not events:
            return self.t(
                f"{label}: nic w kalendarzu.{note}", f"{label}: nothing in the calendar.{note}"
            )
        lines = []
        for at, event in events:
            when = f"{at:%H:%M}" if isinstance(at, datetime) else self.t("cały dzień", "all day")
            where = f" ({event['location']})" if event.get("location") else ""
            lines.append(f"- {when} {event.get('summary', '?')}{where}")
        return f"{label}:\n" + "\n".join(lines)


# ------------------------------------------------------------------- mail ---


def _decode(value: str | None) -> str:
    if not value:
        return ""
    return str(email.header.make_header(email.header.decode_header(value)))


class MailSkill(Skill):
    """``[skills.mail] host = "imap.gmail.com"``, ``user = "you@gmail.com"``."""

    kind = "mail"
    description = "unread mail in the user's inbox (read-only)"

    def _unread(self) -> tuple[int, list[dict[str, str]]]:
        host, user = self.options["host"], self.options["user"]
        password = os.environ.get(self.options.get("password_secret", "DIA_MAIL_PASSWORD"), "")
        with imaplib.IMAP4_SSL(host, int(self.options.get("port", 993))) as box:
            box.login(user, password)
            box.select(self.options.get("folder", "INBOX"), readonly=True)
            _, data = box.search(None, "UNSEEN")
            ids = data[0].split()
            latest = []
            for msg_id in ids[-int(self.options.get("count", 8)) :][::-1]:
                _, parts = box.fetch(msg_id, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
                raw = parts[0][1] if parts and isinstance(parts[0], tuple) else b""
                message = email.message_from_bytes(raw)
                name, address = email.utils.parseaddr(_decode(message.get("From")))
                latest.append({"from": name or address, "subject": _decode(message.get("Subject"))})
            return len(ids), latest

    async def run(self, args: dict[str, Any]) -> str:
        if not self.options.get("host") or not self.options.get("user"):
            return self.t(
                "Nie znam Twojej skrzynki: ustaw [skills.mail] host i user oraz sekret "
                "DIA_MAIL_PASSWORD (dla Gmaila hasło aplikacji).",
                "I don't know your mailbox: set [skills.mail] host and user, and the secret "
                "DIA_MAIL_PASSWORD (for Gmail an app password).",
            )
        try:
            count, latest = await asyncio.to_thread(self._unread)
        except (imaplib.IMAP4.error, OSError) as exc:
            return self.t(f"Nie mogę odczytać poczty: {exc}", f"I can't read the mail: {exc}")
        if not count:
            return self.t("Brak nowych wiadomości.", "No new mail.")
        lines = "\n".join(f"- {m['from']}: {m['subject']}" for m in latest)
        return self.t(f"Nieprzeczytane: {count}\n", f"Unread: {count}\n") + lines


# ------------------------------------------------------------------- home ---

SENSITIVE = ("lock", "alarm_control_panel", "cover", "garage", "valve")
SERVICES = {
    "on": "turn_on",
    "off": "turn_off",
    "toggle": "toggle",
    "open": "open_cover",
    "close": "close_cover",
    "lock": "lock",
    "unlock": "unlock",
}


class HomeSkill(Skill):
    """``[skills.home] url = "http://homeassistant.local:8123"``; token: secret HA_TOKEN."""

    kind = "home"
    description = (
        "Home Assistant: turn lights/switches/scenes/scripts on or off, open/close covers, "
        "lock/unlock, or tell the state of a device"
    )
    args = {"action": "on|off|toggle|open|close|lock|unlock|status", "target": "device/scene name"}

    def _request(self, path: str, body: dict | None = None) -> Any:
        token = os.environ.get(self.options.get("token_secret", "HA_TOKEN"), "")
        req = urllib.request.Request(
            self.options["url"].rstrip("/") + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read() or b"null")

    def match(self, states: list[dict[str, Any]], target: str) -> dict[str, Any] | None:
        """The entity whose name or id is closest to ``target`` (None if nothing close)."""
        target = target.lower().strip()
        best, score = None, 0.0
        for state in states:
            name = str(state.get("attributes", {}).get("friendly_name", "")).lower()
            entity = state["entity_id"].lower()
            s = max(
                SequenceMatcher(None, target, name).ratio(),
                SequenceMatcher(None, target, entity.split(".", 1)[-1].replace("_", " ")).ratio(),
                1.0 if target and (target == entity or target in name) else 0.0,
            )
            if s > score:
                best, score = state, s
        return best if score >= 0.6 else None

    async def run(self, args: dict[str, Any]) -> str:
        if not self.options.get("url"):
            return self.t(
                "Nie znam Twojego Home Assistanta: ustaw [skills.home] url i sekret HA_TOKEN.",
                "I don't know your Home Assistant: set [skills.home] url and the secret HA_TOKEN.",
            )
        states = await asyncio.to_thread(self._request, "/api/states")
        action = str(args.get("action") or "status").lower()
        target = str(args.get("target") or "")
        if action == "status" and not target:
            on = [s for s in states if s["entity_id"].startswith("light.") and s["state"] == "on"]
            names = ", ".join(s["attributes"].get("friendly_name", s["entity_id"]) for s in on)
            return self.t(
                f"Włączone światła: {names or 'żadne'}.", f"Lights on: {names or 'none'}."
            )
        entity = self.match(states, target)
        if not entity:
            return self.t(f"Nie znam urządzenia „{target}”.", f"I don't know “{target}”.")
        entity_id = entity["entity_id"]
        name = entity["attributes"].get("friendly_name", entity_id)
        if action == "status":
            return f"{name}: {entity['state']}"
        domain = entity_id.split(".")[0]
        service = "turn_on" if domain in ("scene", "script") else SERVICES.get(action)
        if not service:
            return self.t(f"Nie umiem: {action}.", f"I can't do: {action}.")

        async def call() -> str:
            await asyncio.to_thread(
                self._request, f"/api/services/{domain}/{service}", {"entity_id": entity_id}
            )
            self.dia.audit("home.call", entity_id, service)
            return self.t(f"Zrobione: {name} ({action}).", f"Done: {name} ({action}).")

        if domain in SENSITIVE or any(word in entity_id for word in SENSITIVE):
            raise NeedsConfirmation(
                self.t(
                    f"{name}: {action}? Powiedz tak albo nie.", f"{name}: {action}? Say yes or no."
                ),
                call,
            )
        return await call()


# ----------------------------------------------------------------- notion ---

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def _plain(rich: list[dict[str, Any]]) -> str:
    return "".join(part.get("plain_text", "") for part in rich or [])


def _title(page: dict[str, Any]) -> str:
    for prop in page.get("properties", {}).values():
        if prop.get("type") == "title":
            return _plain(prop.get("title", [])) or "(untitled)"
    return _plain(page.get("title", [])) or "(untitled)"


class NotionSkill(Skill):
    """Notion: find and read your pages, add notes.

    Create an internal integration (notion.so/my-integrations), share the pages
    Dia may use with it, and keep its token as the secret NOTION_TOKEN.
    New notes go into ``[skills.notion] parent`` (a page or database id).
    """

    kind = "notion"
    description = (
        "the user's Notion: search pages, read a page, or add a note (to their Notion inbox page)"
    )
    args = {
        "action": "search|read|add",
        "query": "words to look for, or the page to read",
        "title": "title of a new note",
        "text": "content of a new note",
    }

    def _request(self, method: str, path: str, body: dict | None = None) -> Any:
        token = os.environ.get(self.options.get("token_secret", "NOTION_TOKEN"), "")
        req = urllib.request.Request(
            NOTION_API + path,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": NOTION_VERSION,
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read() or b"null")

    async def call(self, method: str, path: str, body: dict | None = None) -> Any:
        return await asyncio.to_thread(self._request, method, path, body)

    async def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        found = await self.call(
            "POST",
            "/search",
            {"query": query, "page_size": limit, "filter": {"property": "object", "value": "page"}},
        )
        return found.get("results", [])

    async def read(self, page_id: str, limit: int = 3000) -> str:
        blocks = await self.call("GET", f"/blocks/{page_id}/children?page_size=100")
        lines = []
        for block in blocks.get("results", []):
            kind = block.get("type", "")
            text = _plain(block.get(kind, {}).get("rich_text", []))
            if text:
                prefix = {"bulleted_list_item": "- ", "numbered_list_item": "1. ", "to_do": "☐ "}
                lines.append(prefix.get(kind, "") + text)
        return "\n".join(lines)[:limit]

    async def add(self, title: str, text: str) -> dict[str, Any]:
        parent = str(self.options.get("parent", "")).replace("-", "")
        is_db = bool(self.options.get("parent_is_database"))
        paragraphs = [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": p[:1900]}}]},
            }
            for p in text.split("\n\n")
            if p.strip()
        ]
        title_prop = {"title": [{"type": "text", "text": {"content": title[:200]}}]}
        return await self.call(
            "POST",
            "/pages",
            {
                "parent": {"database_id": parent} if is_db else {"page_id": parent},
                "properties": {self.options.get("title_property", "Name"): title_prop}
                if is_db
                else {"title": title_prop},
                "children": paragraphs[:100],
            },
        )

    async def run(self, args: dict[str, Any]) -> str:
        if not os.environ.get(self.options.get("token_secret", "NOTION_TOKEN")):
            return self.t(
                "Nie mam dostępu do Notion: zapisz token integracji jako sekret NOTION_TOKEN.",
                "I have no access to Notion: save the integration token as the secret "
                "NOTION_TOKEN.",
            )
        action = str(args.get("action") or "search").lower()
        query = str(args.get("query") or "").strip()
        try:
            if action == "add":
                if not self.options.get("parent"):
                    return self.t(
                        "Gdzie zapisywać notatki? Ustaw [skills.notion] parent (id strony).",
                        "Where should notes go? Set [skills.notion] parent (a page id).",
                    )
                text = str(args.get("text") or query).strip()
                title = str(args.get("title") or text.splitlines()[0][:60] or "Dia").strip()
                page = await self.add(title, text)
                self.dia.audit("notion.add", page.get("id"), title)
                return self.t(f"Dodane do Notion: {title}.", f"Added to Notion: {title}.")
            pages = await self.search(query)
            if not pages:
                return self.t(f"Nic w Notion o „{query}”.", f"Nothing in Notion about “{query}”.")
            if action == "read":
                page = pages[0]
                body = await self.read(page["id"])
                return f"{_title(page)}\n\n{body or self.t('(pusta strona)', '(empty page)')}"
            return "\n".join(f"- {_title(p)}" for p in pages)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:200]
            return self.t(
                f"Notion odmówił ({exc.code}): {detail}", f"Notion said no ({exc.code}): {detail}"
            )
