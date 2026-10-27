"""A brain without a model: recognises a few fixed phrases, instantly and for free.

Put it first in the chain; anything it does not recognise goes to the next brain.
"""

from __future__ import annotations

import re

from dia.brains import Brain, BrainContext, Intent

# How speech recognition tends to write "Dia, ..." / "Hey Jarvis, ..." at the start:
# "Dia,", "Dias", "Dzia", "Dija", "Hej Dia", "Hej, Jarvis." and also glued on,
# as in "Dziastatus" or "DIASTATUS".
_ADDRESS = re.compile(
    r"^\s*(?:(?:hej|hey|hi)\W+)?(?:jarvis|dia|dias|dzia|dija|dya)(?:\W+|(?=status|zadania))",
    re.IGNORECASE,
)

_RULES = [
    (
        "stop",
        re.compile(
            r"^(zatrzymaj wszystko|stop wszystko|stop all|stop everything|awaryjny stop|"
            r"emergency stop|wstrzymaj wszystko)\W*$",
            re.I,
        ),
    ),
    (
        "quiet_on",
        re.compile(r"^(tryb cichy|bądź cicho|badz cicho|cisza|quiet mode|be quiet)\W*$", re.I),
    ),
    (
        "quiet_off",
        re.compile(
            r"^(wyłącz tryb cichy|wylacz tryb cichy|możesz mówić|mozesz mowic|"
            r"quiet mode off|you can talk)\W*$",
            re.I,
        ),
    ),
    (
        "screen_on",
        re.compile(
            r"^(możesz patrzeć na ekran|mozesz patrzec na ekran|włącz dostęp do ekranu|"
            r"wlacz dostep do ekranu|you can look at the screen|screen access on)\W*$",
            re.I,
        ),
    ),
    (
        "screen_off",
        re.compile(
            r"^(nie patrz na ekran|wyłącz dostęp do ekranu|wylacz dostep do ekranu|"
            r"stop looking at the screen|screen access off)\W*$",
            re.I,
        ),
    ),
    (
        "camera_on",
        re.compile(
            r"^(możesz patrzeć przez kamerę|mozesz patrzec przez kamere|włącz kamerę|"
            r"wlacz kamere|camera access on|you can use the camera)\W*$",
            re.I,
        ),
    ),
    (
        "camera_off",
        re.compile(
            r"^(wyłącz kamerę|wylacz kamere|nie patrz przez kamerę|nie patrz przez kamere|"
            r"camera access off|stop using the camera)\W*$",
            re.I,
        ),
    ),
    (
        "howto",
        re.compile(
            r"^(zapamiętaj,? jak to zrobiłeś|zapamietaj,? jak to zrobiles|"
            r"zapamiętaj,? jak to zrobiłaś|zapamietaj,? jak to zrobilas|"
            r"remember how you did (?:it|that))\W*$",
            re.I,
        ),
    ),
    (
        "prefer",
        re.compile(r"^(?:zapamiętaj|zapamietaj|remember),? (?:że|ze|that) (?P<text>.+?)\W*$", re.I),
    ),
    ("process", re.compile(r"^(?:zamknij|zabij|ubij|kill|close) (?P<name>[\w.+-]+)\W*$", re.I)),
    ("resume", re.compile(r"^(wznów|wznow|wznów pracę|wznow prace|resume|carry on)\W*$", re.I)),
    ("status", re.compile(r"^(status|stan|co słychać|co slychac|how are things)\W*$", re.I)),
    ("tasks", re.compile(r"^(tasks|zadania|lista zadań|lista zadan|ostatnie zadania)\W*$", re.I)),
]

# Everyday skills: (skill, pattern); a named group "place" becomes an argument.
_SKILLS = [
    (
        "weather",
        re.compile(
            r"^(?:jaka (?:jest )?|what'?s the |how'?s the )?(?:pogoda|weather)"
            r"(?P<tomorrow> (?:na )?jutro| tomorrow)?"
            r"(?: (?:w|we|in|dla|for) (?P<place>[\w .-]+?))?\W*$",
            re.I,
        ),
    ),
    (
        "system",
        re.compile(
            r"^(?:jak tam komputer|stan komputera|zasoby|ile mam ram\w*|temperatura procesora|"
            r"(?P<top>co (?:zjada|zużywa|zuzywa) (?:procesor|ram|pamięć|pamiec))|"
            r"how(?:'s| is) the computer|system status|(?P<top2>what(?:'s| is) using the cpu))\W*$",
            re.I,
        ),
    ),
    (
        "services",
        re.compile(
            r"^(?:czy usługi działają|usługi|stan usług|services|are services up)\W*$", re.I
        ),
    ),
    (
        "updates",
        re.compile(
            r"^(?:aktualizacje|są aktualizacje|sa aktualizacje|sprawdź aktualizacje|"
            r"sprawdz aktualizacje|updates|check (?:for )?updates)\W*$",
            re.I,
        ),
    ),
    (
        "screen",
        re.compile(
            r"^(?P<question>co (?:jest|widzisz) na ekranie|spójrz na ekran|spojrz na ekran|"
            r"what(?:'s| is) on (?:my|the) screen|look at (?:my|the) screen)\W*$",
            re.I,
        ),
    ),
    (
        "clipboard",
        re.compile(
            r"^(?:co (?:mam|jest) w schowku|schowek|pokaż schowek|pokaz schowek|"
            r"what(?:'s| is) (?:in )?(?:my|the) clipboard)\W*$",
            re.I,
        ),
    ),
    (
        "tidy",
        re.compile(
            r"^(?:(?P<undo>cofnij porządki|cofnij porzadki|undo tidying)|"
            r"posprzątaj pobrane|posprzataj pobrane|uporządkuj pobrane|uporzadkuj pobrane|"
            r"posprzątaj downloads|tidy (?:up )?(?:my )?downloads)\W*$",
            re.I,
        ),
    ),
    (
        "camera",
        re.compile(
            r"^(?P<question>co widzisz (?:w kamerze|przez kamer[ęe])|spójrz przez kamerę|"
            r"spojrz przez kamere|zrób zdjęcie|zrob zdjecie|"
            r"what do you see (?:on|through) the camera|look through the camera)\W*$",
            re.I,
        ),
    ),
    (
        "security",
        re.compile(
            r"^(?:raport bezpieczeństwa|raport bezpieczenstwa|bezpieczeństwo|bezpieczenstwo|"
            r"sprawdź bezpieczeństwo|sprawdz bezpieczenstwo|security report|security check)\W*$",
            re.I,
        ),
    ),
    (
        "calendar",
        re.compile(
            r"^(?:co mam (?P<tomorrow>jutro|dziś|dzis|dzisiaj)|kalendarz|plan dnia|"
            r"what(?:'s| is) on (?:my calendar|today)|my calendar)\W*$",
            re.I,
        ),
    ),
    (
        "mail",
        re.compile(r"^(?:poczta|maile|nowe maile|czy mam maile|mail|any mail|my mail)\W*$", re.I),
    ),
    ("news", re.compile(r"^(?:co nowego|newsy|wiadomości|wiadomosci|news|headlines)\W*$", re.I)),
    (
        "stocks",
        re.compile(r"^(?:giełda|gielda|notowania|kursy|akcje|stocks|markets?)\W*$", re.I),
    ),
    (
        "crypto",
        re.compile(
            r"^(?:krypto|kryptowaluty|kursy krypto(?:walut)?|bitcoin|btc|crypto|cryptos?)\W*$",
            re.I,
        ),
    ),
    (
        "briefing",
        re.compile(
            r"^(?:dzień dobry|dzien dobry|briefing|podsumowanie dnia|good morning)\W*$", re.I
        ),
    ),
]


def strip_address(text: str) -> str:
    """The request without the way the user addressed Dia."""
    return _ADDRESS.sub("", text.strip()).strip()


class RulesBrain(Brain):
    kind = "rules"

    async def interpret(self, text: str, ctx: BrainContext) -> Intent | None:
        cleaned = strip_address(text)
        for action, pattern in _RULES:
            if match := pattern.match(cleaned):
                if action == "process":
                    return Intent("process", args={"name": match.group("name")})
                if action == "prefer":
                    return Intent("prefer", args={"text": match.group("text")})
                if action.startswith("camera_"):
                    return Intent("camera_access", args={"on": action == "camera_on"})
                if action.startswith("screen_"):
                    return Intent("screen_access", args={"on": action == "screen_on"})
                if action.startswith("quiet_"):
                    return Intent("quiet", args={"on": action == "quiet_on"})
                return Intent(action)
        for skill, pattern in _SKILLS:
            if skill in ctx.skills and (match := pattern.match(cleaned)):
                groups = match.groupdict()
                args = {k: v.strip() for k, v in groups.items() if v and k == "place"}
                if groups.get("top") or groups.get("top2"):
                    args["top"] = "true"
                if groups.get("undo"):
                    args["undo"] = "true"
                if groups.get("question"):
                    args["question"] = groups["question"]
                if (when := match.groupdict().get("tomorrow")) and when.strip().lower() in (
                    "jutro",
                    "na jutro",
                    "tomorrow",
                ):
                    args["day"] = "tomorrow"
                return Intent("skill", skill=skill, args=args)
        return None
