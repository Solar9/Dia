"""Prompt helpers shared by the orchestrator and its collaborators."""

from __future__ import annotations

# Appended to every instruction that lets an agent edit files. Without it agents
# try `git commit` themselves, get blocked by their permissions, and report the
# work as "not committed, waiting for approval" although Dia commits it.
EDIT_NOTE = """

---
Notes from Dia, which runs this task:
- Work only in the current directory.
- Do not commit: when you finish, Dia commits your changes and runs the
  project's tests itself. You may run tests or checks if your tools allow it.
- End with a short summary of what you changed and anything left undone."""


def with_context(prompt: str, context: str) -> str:
    if not context:
        return prompt
    return (
        "Background for this task (notes may be outdated; the code is the source of truth):\n\n"
        f"{context}\n\n---\n\nTask:\n{prompt}"
    )


def _title(prompt: str) -> str:
    line = prompt.strip().splitlines()[0] if prompt.strip() else "Dia task"
    return line if len(line) <= 72 else line[:71].rstrip() + "…"
