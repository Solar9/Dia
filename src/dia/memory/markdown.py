"""Memory in a folder of Markdown notes, compatible with an Obsidian vault.

Dia writes only inside its own folder of the vault (``folder``, "Dia" by
default). What it may *read* for context is set by ``search``: ``"folder"``
(the default: only its own folder), ``"vault"`` (any note, minus ``exclude``
patterns, hidden folders and notes marked ``dia: private`` in frontmatter) or
``"off"``::

    <vault>/Dia/
      Profile.md           what every agent should know about you (you write it)
      Projects/<name>.md   per-project knowledge, created as a template (you fill it)
      Journal/<date>.md    what the agents did; Dia only ever appends here
      How-tos/<title>.md   procedures ("how we export a build"), handed to the
                           agents when a task matches their ``when`` (frontmatter)

Notes are plain Markdown, so the vault works with Obsidian (and Obsidian
Sync), any other editor, or git. Dia never rewrites a note you can edit:
it creates missing project templates and appends to the journal, nothing more.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dia.memory import Memory
from dia.memory.search import Hit, query_stems, search
from dia.memory.semantic import OpenAIEmbedder, SemanticIndex, fuse

if TYPE_CHECKING:
    from dia.config import ProjectConfig
    from dia.orchestrator import TaskReport

log = logging.getLogger("dia.memory")

_FRONTMATTER = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)

PROJECT_TEMPLATE = """\
---
tags: [dia/project]
project: {name}
path: {path}
---
# {title}

<!-- Dia adds this note to every task it runs on this project. Write what an
agent should know before touching the code: stack, architecture, conventions,
known problems, things not to change. Sections left empty are skipped. -->

## Overview

## Architecture

## Conventions

## Known issues
"""


def _meta(text: str) -> dict[str, str]:
    """Simple ``key: value`` lines of a note's frontmatter."""
    fm = _FRONTMATTER.match(text)
    meta = {}
    for line in fm.group(0).splitlines()[1:-1] if fm else []:
        key, sep, value = line.partition(":")
        if sep and key.strip() and not key.startswith(" "):
            meta[key.strip()] = value.strip().strip('"').strip("'")
    return meta


def _clean(text: str) -> str:
    """Note body without frontmatter, comments, or a template nobody filled in."""
    text = _COMMENT.sub("", _FRONTMATTER.sub("", text)).strip()
    if all(line.lstrip().startswith("#") for line in text.splitlines() if line.strip()):
        return ""
    return text


def _quote(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) > limit:
        text = text[:limit].rstrip() + " …"
    return "\n".join(f"> {line}" if line else ">" for line in text.splitlines())


class MarkdownMemory(Memory):
    kind = "markdown"

    def __init__(self, options: dict | None = None) -> None:
        super().__init__(options)
        if "vault" not in self.options:
            raise ValueError("[memory] type 'markdown' requires 'vault' (path to the vault folder)")
        vault = os.path.expandvars(str(self.options["vault"]))
        self.vault = Path(vault).expanduser().resolve()
        self.folder = self.options.get("folder", "Dia")
        self.root = self.vault / self.folder
        self.projects_dir = self.options.get("projects_dir", "Projects")
        self.journal_dir = self.options.get("journal_dir", "Journal")
        self.profile = self.options.get("profile_note", "Profile.md")
        self.howtos_dir = self.options.get("howtos_dir", "How-tos")
        self.max_context = int(self.options.get("max_context_chars", 8000))
        self.search_scope = self.options.get("search", "folder")
        if self.search_scope not in ("folder", "vault", "off"):
            raise ValueError("[memory] search must be 'folder', 'vault' or 'off'")
        self._index: SemanticIndex | None = None

    def describe(self) -> str:
        return f"{self.kind}  {self.root}  (search: {self.search_scope})"

    def check(self) -> str | None:
        if not self.vault.is_dir():
            return f"vault folder does not exist: {self.vault}"
        return None

    def project_note(self, project: ProjectConfig) -> Path:
        name = project.options.get("note", project.name)
        return self.root / self.projects_dir / f"{name}.md"

    def _link(self, project: ProjectConfig) -> str:
        note = self.project_note(project).relative_to(self.vault).with_suffix("")
        return f"[[{note.as_posix()}|{project.name}]]"

    def semantic_index(self) -> SemanticIndex | None:
        """The vector index, when ``semantic`` is configured."""
        options = self.options.get("semantic")
        if not options or self.search_scope == "off":
            return None
        if self._index is None:
            options = {} if options is True else dict(options)
            embedder = OpenAIEmbedder(options)
            self._index = SemanticIndex(
                Path(self.options.get("index_dir", self.vault)) / "memory-index.db",
                self.vault,
                self.vault if self.search_scope == "vault" else self.root,
                list(self.options.get("exclude", [])),
                embedder,
                embedder.model,
            )
        return self._index

    def search(self, query: str, limit: int = 5, skip: set[Path] | None = None) -> list[Hit]:
        if self.search_scope == "off" or self.check():
            return []
        keyword = self._keyword_search(query, limit, skip)
        index = self.semantic_index()
        if not index:
            return keyword
        try:
            # Keep the index fresh without making one search wait for a whole vault;
            # `dia memory index` (and `dia serve`) do the full pass.
            index.update(max_notes=int(self.options.get("index_per_search", 10)))
            rel_skip = {p.resolve().relative_to(self.vault).as_posix() for p in skip or set()}
            semantic = index.search(query, limit, rel_skip)
        except Exception as exc:  # the embedding server is down: words still work
            log.warning("semantic search unavailable: %s", exc)
            return keyword
        return fuse(semantic, keyword, limit=limit)

    def _keyword_search(
        self, query: str, limit: int = 5, skip: set[Path] | None = None
    ) -> list[Hit]:
        return search(
            self.vault,
            self.vault if self.search_scope == "vault" else self.root,
            query,
            exclude=list(self.options.get("exclude", [])),
            skip=skip,
            limit=limit,
            snippet_chars=int(self.options.get("snippet_chars", 600)),
        )

    def context_for(self, project: ProjectConfig, task: str) -> str:
        if self.check():
            return ""
        note = self.project_note(project)
        if not note.exists() and self.options.get("create_project_notes", True):
            note.parent.mkdir(parents=True, exist_ok=True)
            note.write_text(
                PROJECT_TEMPLATE.format(
                    name=project.name, title=project.name.capitalize(), path=project.path
                )
            )
        sections = []
        profile = self.root / self.profile
        if profile.is_file() and (body := _clean(profile.read_text())):
            sections.append(f"## About the user\n\n{body}")
        if note.is_file() and (body := _clean(note.read_text())):
            sections.append(f"## Project notes: {project.name}\n\n{body}")
        howtos = self.matching_howtos(project.name, task)
        if howtos:
            listing = "\n\n".join(f"### {h['title']}\n\n{h['steps']}" for h in howtos)
            sections.append(f"## How-tos (follow them where they apply)\n\n{listing}")
        hits = self.search(
            f"{project.name} {task}",
            limit=int(self.options.get("search_results", 5)),
            # how-tos come only through matching: another project's would be noise
            skip={profile, note, *(self.root / h["path"] for h in self.howtos())},
        )
        if hits:
            related = "\n\n".join(f"### {hit.link}\n\n{hit.snippet}" for hit in hits)
            sections.append(f"## Related notes (excerpts)\n\n{related}")
        context = "\n\n".join(sections)
        if len(context) > self.max_context:
            context = context[: self.max_context].rstrip() + "\n\n[... notes truncated]"
        return context

    # ------------------------------------------------------------- how-tos ---

    def howtos(self) -> list[dict[str, Any]]:
        folder = self.root / self.howtos_dir
        if self.check() or not folder.is_dir():
            return []
        found = []
        for path in sorted(folder.glob("*.md")):
            text = path.read_text(errors="replace")
            meta = _meta(text)
            projects = [p.strip() for p in meta.get("projects", "").strip("[]").split(",")]
            found.append(
                {
                    "path": path.relative_to(self.root).as_posix(),
                    "title": meta.get("title") or path.stem,
                    "when": meta.get("when", ""),
                    "projects": [p for p in projects if p],
                    "steps": _clean(text),
                }
            )
        return found

    def matching_howtos(self, project: str, task: str) -> list[dict[str, Any]]:
        """How-tos for this project (or any) whose title or ``when`` share words with the task."""
        stems = query_stems(task)
        ranked = []
        for howto in self.howtos():
            if howto["projects"] and project not in howto["projects"]:
                continue
            words = query_stems(f"{howto['title']} {howto['when']}")
            score = sum(any(w.startswith(s) or s.startswith(w) for w in words) for s in stems)
            if score and howto["steps"]:
                ranked.append((score, howto))
        ranked.sort(key=lambda r: -r[0])
        return [h for _, h in ranked[: int(self.options.get("howto_results", 3))]]

    def save_howto(
        self, title: str, when: str, steps: str, projects: list[str] | None = None
    ) -> str:
        if problem := self.check():
            raise RuntimeError(problem)
        name = re.sub(r'[\\/:*?"<>|#^\[\]]+', " ", title).strip()[:80] or "How-to"
        path = self.root / self.howtos_dir / f"{name}.md"
        n = 2
        while path.exists():
            path, n = self.root / self.howtos_dir / f"{name} {n}.md", n + 1
        path.parent.mkdir(parents=True, exist_ok=True)
        when_line = " ".join(when.split()).replace('"', "'")
        front = ["---", "tags: [dia/howto]", f'when: "{when_line}"']
        if projects:
            front.append(f"projects: [{', '.join(projects)}]")
        front.append("---")
        path.write_text("\n".join(front) + f"\n# {title}\n\n{steps.strip()}\n")
        return path.relative_to(self.root).as_posix()

    # ------------------------------------------------------------ browsing ---

    def _note_path(self, path: str) -> Path:
        """A note inside Dia's own folder; anything else is refused."""
        target = (self.root / path).resolve()
        if target.suffix != ".md" or not target.is_relative_to(self.root.resolve()):
            raise ValueError(f"not a note in {self.folder}/: {path}")
        return target

    def notes(self) -> list[dict[str, Any]]:
        if self.check() or not self.root.is_dir():
            return []
        found = []
        for path in sorted(self.root.rglob("*.md")):
            rel = path.relative_to(self.root)
            if any(part.startswith(".") for part in rel.parts):
                continue
            top = rel.parts[0] if len(rel.parts) > 1 else ""
            kind = (
                "profile"
                if rel.as_posix() == self.profile
                else "project"
                if top == self.projects_dir
                else "journal"
                if top == self.journal_dir
                else "howto"
                if top == self.howtos_dir
                else "other"
            )
            stat = path.stat()
            found.append(
                {
                    "path": rel.as_posix(),
                    "title": path.stem,
                    "kind": kind,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime)
                    .astimezone()
                    .isoformat(timespec="seconds"),
                }
            )
        return found

    def read_note(self, path: str) -> str:
        return self._note_path(path).read_text(errors="replace")

    def write_note(self, path: str, text: str) -> None:
        target = self._note_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def remember(self, project: ProjectConfig, facts: list[str]) -> None:
        """Append facts to the project note's learned section, never editing the rest."""
        if problem := self.check():
            raise RuntimeError(problem)
        note = self.project_note(project)
        note.parent.mkdir(parents=True, exist_ok=True)
        text = (
            note.read_text()
            if note.exists()
            else PROJECT_TEMPLATE.format(
                name=project.name, title=project.name.capitalize(), path=project.path
            )
        )
        heading = self.options.get("learned_heading", "## Learned by Dia")
        sections = re.findall(r"^## .*$", text, re.MULTILINE)
        addition = "" if text.endswith("\n") else "\n"
        if not sections or sections[-1].strip() != heading:
            addition += f"\n{heading}\n\n"
        today = datetime.now().astimezone()
        addition += "".join(f"- {fact} ({today:%Y-%m-%d})\n" for fact in facts)
        if note.exists():
            with note.open("a") as fh:
                fh.write(addition)
        else:
            note.write_text(text + addition)

    def record(self, project: ProjectConfig, report: TaskReport) -> None:
        if not self.options.get("journal", True) or self.check():
            return
        task = report.task
        started = datetime.fromisoformat(task.created_at).astimezone()
        journal = self.root / self.journal_dir / f"{started:%Y-%m-%d}.md"
        journal.parent.mkdir(parents=True, exist_ok=True)

        title = task.prompt.splitlines()[0][:80]
        tests = {None: "not run", True: "passed", False: "FAILED"}[task.tests_ok]
        lines = [
            f"## {started:%H:%M} · {self._link(project)} · {title}",
            "",
            f"- status: **{task.status}** · agent: {task.agent} · mode: {task.mode} "
            f"· tests: {tests}",
        ]
        if task.commit_sha:
            lines.append(f"- branch: `{task.branch}` @ `{task.commit_sha[:10]}`")
        lines.append(f"- task: `{task.id}`")
        if task.error:
            lines.append(f"- error: {task.error.splitlines()[0][:300]}")
        if task.summary:
            lines += [
                "",
                _quote(task.summary, int(self.options.get("journal_summary_chars", 1500))),
            ]

        header = "" if journal.exists() else f"# {started:%Y-%m-%d}\n"
        with journal.open("a") as fh:
            fh.write(header + "\n" + "\n".join(lines) + "\n")
