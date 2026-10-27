"""Forges: where task branches go when you approve them (push, pull/merge requests).

Authentication stays with the tools you already use (git credentials, ``gh``,
``glab``); Dia stores no tokens. ``forge = "auto"`` (the default) picks the
forge from the remote's URL.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from dia.workspace import GitError, git, run


@dataclass
class Publication:
    url: str | None  # pull/merge request URL, when one was opened
    message: str  # human-readable outcome


@dataclass
class CIStatus:
    state: str  # none | pending | success | failed
    url: str | None = None
    # Failed jobs/checks: {"name": ..., "id": ..., "url": ...}
    failed: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ReviewComment:
    id: str  # unique per forge, e.g. "inline-123"
    author: str
    body: str
    path: str | None = None  # file and line for inline comments
    line: int | None = None
    url: str | None = None

    @property
    def is_bot(self) -> bool:
        return self.author.endswith("[bot]") or self.author.endswith("-bot")


@dataclass
class Issue:
    number: int
    title: str
    body: str = ""
    author: str = ""
    url: str | None = None


class Forge(ABC):
    kind: ClassVar[str]
    has_ci: ClassVar[bool] = True  # False: nothing to watch after publishing

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        self.options: dict[str, Any] = dict(options or {})

    @property
    def remote(self) -> str:
        return self.options.get("remote", "origin")

    def check(self) -> str | None:
        return None

    async def push(self, repo: Path, branch: str, *push_options: str) -> str:
        argv = ["git", "push", "--set-upstream"]
        for option in push_options:
            argv += ["-o", option]
        code, out = await run([*argv, self.remote, branch], repo)
        if code != 0:
            raise GitError(f"git push failed: {out.strip()}")
        return out

    async def ci_status(self, repo: Path, branch: str) -> CIStatus:
        """CI state of the branch's pull/merge request; forges without CI say "none"."""
        return CIStatus("none")

    async def ci_log(self, repo: Path, status: CIStatus, max_chars: int = 6000) -> str:
        """Log excerpts of the failed jobs, for an agent to fix them."""
        return ""

    async def review_comments(self, repo: Path, branch: str) -> list[ReviewComment]:
        """Comments on the branch's pull/merge request (reviews, threads, inline notes)."""
        return []

    async def issues(self, repo: Path, label: str) -> list[Issue]:
        """Open issues carrying ``label``; forges without issues return nothing."""
        return []

    @abstractmethod
    async def publish(
        self, repo: Path, branch: str, base: str, title: str, body: str
    ) -> Publication: ...


def find_url(text: str, marker: str) -> str | None:
    match = re.search(rf"https?://\S+{marker}\S*", text)
    return match.group(0).rstrip(".,)") if match else None


async def detect(repo: Path, remote: str = "origin") -> str:
    """'github', 'gitlab' or 'git', from the remote's URL."""
    try:
        url = await git(repo, "remote", "get-url", remote)
    except GitError:
        raise GitError(f"the repository has no remote '{remote}' to publish to") from None
    host = re.sub(r"^[a-z+]+://([^@/]+@)?|^[^@]+@", "", url).split("/")[0].split(":")[0].lower()
    if "github" in host:
        return "github"
    if "gitlab" in host:
        return "gitlab"
    return "git"
