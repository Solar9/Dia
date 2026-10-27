"""The behaviour guard: noticing an agent that goes looking for secrets.

Inside the sandbox an agent's home is not empty but a decoy: where real
secrets usually are (``~/.ssh``, ``~/.config/dia/env``, ``~/.aws``,
``~/.netrc``, ``~/.git-credentials``, ``~/.config/gh``) it finds fake ones
carrying a one-off marker. Nothing real can leak; but if the marker shows up
in what the agent says or in the files it changed, it read a "secret" it had
no business reading, usually because instructions hidden in a repository,
issue, web page or note told it to (prompt injection).

That is an incident: recorded on the task (``details.incidents``), in the
audit log and as an urgent alert, and the agent's work is not committed. An
agent that only mentions such paths together with an error ("No such file",
"Permission denied") is recorded as a lesser incident without stopping.

    [sandbox]
    decoys = true     # false: an empty home instead, no incidents
"""

from __future__ import annotations

import re
import secrets
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dia.agents import AgentResult

SENSITIVE = re.compile(
    r"(\.ssh/|id_rsa|id_ed25519|\.config/dia/env|\.aws/credentials|\.netrc|"
    r"\.git-credentials|\.config/gh/hosts|\.gnupg)",
    re.IGNORECASE,
)
REFUSED = re.compile(r"(no such file|permission denied|read-only file system|not permitted)", re.I)
SKIP_DIRS = {".git", "node_modules", ".godot", ".venv", "__pycache__"}


@dataclass
class Incident:
    severity: str  # "high" (a decoy secret was read) or "medium" (an attempt)
    kind: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"severity": self.severity, "kind": self.kind, "detail": self.detail}


@dataclass
class Guard:
    """Decoys for one agent call and the check of what came back."""

    home: Path | None  # the decoy home; None: no decoys, only attempts are noticed
    marker: str
    started: float = field(default_factory=time.time)

    @classmethod
    def start(cls, root: Path, decoys: bool = True) -> Guard:
        marker = f"DIA-DECOY-{secrets.token_hex(8)}"
        if not decoys:
            return cls(home=None, marker=marker)
        home = root / secrets.token_hex(6)
        files = {
            ".ssh/id_ed25519": "-----BEGIN OPENSSH PRIVATE KEY-----\n"
            f"{marker}\n-----END OPENSSH PRIVATE KEY-----\n",
            ".ssh/config": f"Host prod\n  HostName 10.0.0.1\n  # {marker}\n",
            ".config/dia/env": f"HA_TOKEN={marker}\nNOTION_TOKEN={marker}\n",
            ".aws/credentials": f"[default]\naws_access_key_id = AKIA{marker}\n"
            f"aws_secret_access_key = {marker}\n",
            ".netrc": f"machine github.com login dia password {marker}\n",
            ".git-credentials": f"https://dia:{marker}@github.com\n",
            ".config/gh/hosts.yml": f"github.com:\n  oauth_token: {marker}\n",
        }
        for rel, text in files.items():
            path = home / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        return cls(home=home, marker=marker)

    def check(self, result: AgentResult, cwd: Path) -> list[Incident]:
        found: list[Incident] = []
        said = "\n".join(str(x) for x in (result.summary, result.error, result.details) if x)
        if self.marker in said:
            found.append(Incident("high", "decoy-secret-in-output", _excerpt(said, self.marker)))
        for path in self._changed_files(cwd):
            try:
                text = path.read_text(errors="replace")[:1_000_000]
            except OSError:
                continue
            if self.marker in text:
                found.append(Incident("high", "decoy-secret-in-files", str(path.relative_to(cwd))))
        if not found:
            for line in said.splitlines():
                if SENSITIVE.search(line) and REFUSED.search(line):
                    found.append(Incident("medium", "reached-for-secrets", line.strip()[:300]))
                    break
        return found

    def _changed_files(self, cwd: Path) -> list[Path]:
        changed = []
        for path in cwd.rglob("*"):
            if any(part in SKIP_DIRS for part in path.relative_to(cwd).parts):
                continue
            try:
                if path.is_file() and path.stat().st_mtime >= self.started - 1:
                    changed.append(path)
            except OSError:
                continue
        return changed[:2000]

    def cleanup(self) -> None:
        if self.home is not None:
            shutil.rmtree(self.home, ignore_errors=True)


def _excerpt(text: str, marker: str) -> str:
    at = text.find(marker)
    return text[max(0, at - 120) : at + len(marker) + 40].replace(marker, "<decoy>")


def describe(incidents: list[Incident] | list[dict[str, Any]]) -> str:
    rows = [i if isinstance(i, dict) else i.to_dict() for i in incidents]
    return "; ".join(f"[{r['severity']}] {r['kind']}: {r['detail'][:120]}" for r in rows)
