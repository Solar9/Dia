"""Keyword search over a folder of Markdown notes.

No index and no dependencies: the notes are scanned on every search, which is
fast enough for personal vaults of a few thousand notes. Matching is by word
prefix, a crude stemmer that copes with inflected languages ("ekwipunku"
finds "ekwipunek", "systemu" finds "system").
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

_WORD = re.compile(r"[^\W\d_]{3,}|\d{3,}")
_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_PRIVATE = re.compile(r"^dia:\s*(private|false|no|off)\s*$", re.MULTILINE | re.IGNORECASE)

# Words too common to say anything about relevance (English and Polish).
_STOPWORDS = frozenset(
    """
    the and for are but not you all any can had her was one our out has have this that
    with from they will what when where which who why how into than then them these those
    there their about would could should please make add use using does done
    oraz ale nie jak jest się sie czy dla przez przy tak też tez już juz albo lub żeby zeby
    jaki jaka jakie który ktory która ktora które ktore tego tym ten taka takie jego jej ich
    mnie mój moj moja moje twój twoj nam was być byc może moze można mozna trzeba bardzo
    dodaj zrób zrob sprawdź sprawdz proszę prosze chcę chce
    """.split()
)

MAX_FILES = 5000
MAX_BYTES = 512 * 1024


@dataclass
class Hit:
    path: Path  # relative to the searched base (the vault)
    score: float
    snippet: str

    @property
    def link(self) -> str:
        return f"[[{self.path.with_suffix('').as_posix()}]]"


def query_stems(text: str) -> list[str]:
    stems = []
    for word in _WORD.findall(text.lower()):
        if word in _STOPWORDS:
            continue
        stem = word if len(word) <= 4 else word[: max(4, min(6, len(word) - 2))]
        if stem not in stems:
            stems.append(stem)
    return stems


def _matches(stem: str, words: Counter[str]) -> int:
    return sum(n for word, n in words.items() if word.startswith(stem))


def is_private(text: str) -> bool:
    fm = _FRONTMATTER.match(text)
    return bool(fm and _PRIVATE.search(fm.group(1)))


def _excluded(rel: Path, exclude: list[str]) -> bool:
    if any(part.startswith(".") for part in rel.parts):  # .obsidian, .trash, .git
        return True
    posix = rel.as_posix()
    for pattern in exclude:
        # "Private", "Private/", "Private/*" and "Private/**" all mean the whole folder.
        folder = re.sub(r"/(\*\*?)?$", "", pattern.strip())
        if posix.startswith(folder + "/") or fnmatch(posix, pattern):
            return True
    return False


def _snippet(body: str, stems: list[str], limit: int) -> str:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]

    def rank(p: str) -> tuple[int, bool]:
        words = Counter(_WORD.findall(p.lower()))
        # On a tie, a paragraph with content beats a bare heading.
        return sum(1 for s in stems if _matches(s, words)), not p.startswith("#")

    best = max(paragraphs, key=rank, default="")
    return best if len(best) <= limit else best[:limit].rstrip() + " …"


def search(
    base: Path,
    root: Path,
    query: str,
    *,
    exclude: list[str] | None = None,
    skip: set[Path] | None = None,
    limit: int = 5,
    snippet_chars: int = 600,
) -> list[Hit]:
    """Best-matching notes under ``root``; paths in hits are relative to ``base``."""
    stems = query_stems(query)
    if not stems or not root.is_dir():
        return []
    exclude, skip = exclude or [], {p.resolve() for p in (skip or set())}

    notes: list[tuple[Path, str, Counter[str], Counter[str]]] = []
    for path in sorted(root.rglob("*.md"))[:MAX_FILES]:
        rel = path.relative_to(base)
        if path.resolve() in skip or _excluded(rel, exclude):
            continue
        try:
            if path.stat().st_size > MAX_BYTES:
                continue
            text = path.read_text(errors="replace")
        except OSError:
            continue
        if is_private(text):
            continue
        body = _FRONTMATTER.sub("", text)
        notes.append(
            (
                rel,
                body,
                Counter(_WORD.findall(body.lower())),
                Counter(_WORD.findall(path.stem.lower())),
            )
        )

    df = {
        s: sum(1 for _, _, words, title in notes if _matches(s, words) or _matches(s, title))
        for s in stems
    }
    hits = []
    for rel, body, words, title in notes:
        score = 0.0
        for s in stems:
            if not df[s]:
                continue
            idf = math.log(1 + len(notes) / df[s])
            if tf := _matches(s, words):
                score += (1 + math.log(tf)) * idf
            if _matches(s, title):
                score += 2 * idf
        if score > 0:
            hits.append(Hit(rel, score, _snippet(body, stems, snippet_chars)))
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:limit]
