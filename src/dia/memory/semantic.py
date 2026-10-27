"""Semantic search over the notes: finds notes by meaning, not only by words
("the inventory bug from two weeks ago" finds a note about "ekwipunek gubi
przedmioty po zapisie").

Notes are split into chunks and turned into vectors by an embedding model
behind any OpenAI-compatible ``/embeddings`` endpoint, by default a local
Ollama (``ollama pull nomic-embed-text``), so the notes never leave the
computer. Vectors are kept in ``<data_dir>/memory-index.db`` and refreshed
for changed notes only::

    [memory]
    semantic = { model = "nomic-embed-text" }   # base_url: http://localhost:11434/v1

Results are merged with the keyword search (reciprocal rank fusion), so exact
names still win and paraphrases are found too.
"""

from __future__ import annotations

import array
import json
import math
import os
import re
import sqlite3
import urllib.request
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from dia.memory.search import _FRONTMATTER, MAX_BYTES, MAX_FILES, Hit, _excluded, is_private

CHUNK_CHARS = 900

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chunks (
    path TEXT NOT NULL,
    mtime REAL NOT NULL,
    model TEXT NOT NULL,
    n INTEGER NOT NULL,
    text TEXT NOT NULL,
    vector BLOB NOT NULL,
    PRIMARY KEY (path, n)
);
"""


def chunks(body: str, size: int = CHUNK_CHARS) -> list[str]:
    """Paragraph-aligned pieces of about ``size`` characters, each with its heading."""
    out, current, heading = [], "", ""
    for para in (p.strip() for p in re.split(r"\n\s*\n", body)):
        if not para:
            continue
        if para.startswith("#"):
            heading = para.splitlines()[0]
        if current and len(current) + len(para) > size:
            out.append(current)
            current = heading + "\n" if heading and not para.startswith("#") else ""
        current += para + "\n\n"
        while len(current) > size * 2:  # one huge paragraph
            out.append(current[:size])
            current = current[size:]
    if current.strip():
        out.append(current)
    return [c.strip() for c in out]


def _norm(vector: list[float]) -> array.array:
    length = math.sqrt(sum(x * x for x in vector)) or 1.0
    return array.array("f", (x / length for x in vector))


def _dot(a: array.array, b: array.array) -> float:
    return sum(x * y for x, y in zip(a, b, strict=False))


class OpenAIEmbedder:
    """``POST {base_url}/embeddings``: Ollama, LM Studio, llama.cpp, OpenAI..."""

    def __init__(self, options: dict[str, Any]) -> None:
        self.model = options.get("model", "nomic-embed-text")
        self.base_url = options.get("base_url", "http://localhost:11434/v1").rstrip("/")
        self.api_key = os.environ.get(options.get("api_key_env", ""), "")
        self.timeout = float(options.get("timeout", 120))
        self.batch = int(options.get("batch", 16))

    def __call__(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch):
            body = json.dumps({"model": self.model, "input": texts[start : start + self.batch]})
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            req = urllib.request.Request(
                f"{self.base_url}/embeddings", data=body.encode(), headers=headers
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read())
            vectors += [
                item["embedding"] for item in sorted(data["data"], key=lambda d: d["index"])
            ]
        return vectors


class SemanticIndex:
    def __init__(
        self,
        db: Path,
        vault: Path,
        root: Path,
        exclude: list[str],
        embed: Callable[[list[str]], list[list[float]]],
        model: str,
    ) -> None:
        self.db_path, self.vault, self.root = db, vault, root
        self.exclude, self.embed, self.model = exclude, embed, model
        db.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(db)
        self.db.executescript(_SCHEMA)

    def _notes(self) -> Iterator[tuple[str, Path, float]]:
        for path in sorted(self.root.rglob("*.md"))[:MAX_FILES]:
            rel = path.relative_to(self.vault)
            if _excluded(rel, self.exclude):
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            if stat.st_size <= MAX_BYTES:
                yield rel.as_posix(), path, stat.st_mtime

    def update(self, max_notes: int | None = None) -> int:
        """Embed new and changed notes (at most ``max_notes``), drop removed ones.
        Returns how many notes were (re)indexed."""
        indexed = {
            path: (mtime, model)
            for path, mtime, model in self.db.execute(
                "SELECT path, mtime, model FROM chunks WHERE n = 0"
            )
        }
        present, done = set(), 0
        for rel, path, mtime in self._notes():
            present.add(rel)
            if indexed.get(rel) == (mtime, self.model):
                continue
            if max_notes is not None and done >= max_notes:
                continue
            text = path.read_text(errors="replace")
            pieces = [] if is_private(text) else chunks(_FRONTMATTER.sub("", text))
            vectors = self.embed([f"{Path(rel).stem}\n{p}" for p in pieces]) if pieces else []
            with self.db:
                self.db.execute("DELETE FROM chunks WHERE path = ?", (rel,))
                rows = [
                    (rel, mtime, self.model, n, piece, _norm(vector).tobytes())
                    for n, (piece, vector) in enumerate(zip(pieces, vectors, strict=True))
                ]
                if not rows:  # remember empty/private notes too, so they aren't re-read
                    rows = [(rel, mtime, self.model, 0, "", array.array("f").tobytes())]
                self.db.executemany("INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?)", rows)
            done += 1
        gone = set(indexed) - present
        with self.db:
            self.db.executemany("DELETE FROM chunks WHERE path = ?", [(p,) for p in gone])
        return done

    def search(self, query: str, limit: int = 5, skip: set[str] | None = None) -> list[Hit]:
        [vector] = self.embed([query])
        q = _norm(vector)
        best: dict[str, tuple[float, str]] = {}
        for path, text, blob in self.db.execute(
            "SELECT path, text, vector FROM chunks WHERE model = ? AND text != ''", (self.model,)
        ):
            if skip and path in skip:
                continue
            v = array.array("f")
            v.frombytes(blob)
            score = _dot(q, v)
            if score > best.get(path, (-2.0, ""))[0]:
                best[path] = (score, text)
        ranked = sorted(best.items(), key=lambda kv: kv[1][0], reverse=True)[:limit]
        return [Hit(Path(path), score, text) for path, (score, text) in ranked]


def fuse(*rankings: list[Hit], limit: int = 5, k: int = 60) -> list[Hit]:
    """Reciprocal rank fusion of several result lists (same note: best snippet kept)."""
    scores: dict[Path, float] = {}
    hits: dict[Path, Hit] = {}
    for ranking in rankings:
        for rank, hit in enumerate(ranking):
            scores[hit.path] = scores.get(hit.path, 0.0) + 1.0 / (k + rank + 1)
            hits.setdefault(hit.path, hit)
    order = sorted(scores, key=scores.__getitem__, reverse=True)[:limit]
    return [Hit(p, round(scores[p] * 100, 2), hits[p].snippet) for p in order]
