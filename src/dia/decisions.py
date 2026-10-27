"""A memory of decisions: what was accepted, what was rejected, and why.

Every merge, discard, rollback, rejected plan and review verdict is a
decision record (the ``decisions`` table), with the reason when you give one
(``dia merge ID --reason "..."``, the reason field in the UI, or what you say
when you turn down a plan). "Dlaczego trzy miesiące temu zrezygnowaliśmy z
X?" (``dia why "X"`` or ask Dia) finds the decisions about X, what came of
them (rolled back later? made the benchmark worse? its tests), and the notes
and commits that mention it.

Finding is by words, forgiving about Polish endings: "zrezygnowaliśmy z
inwentarza ECS" matches a task "inventory as ECS" only through "ECS", so
name the thing, not the feeling.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING, Any

from dia.workspace import GitError, git

if TYPE_CHECKING:
    from dia.orchestrator import Orchestrator

# Words of the question that say nothing about the subject.
STOPWORDS = set(
    """
    dlaczego czemu kiedy jak jaki jaka jakie co czy się sie nie tak nam nas
    zrezygnowaliśmy zrezygnowalismy zrezygnowano odrzuciliśmy odrzucilismy zrobiliśmy
    zrobilismy wybraliśmy wybralismy temu miesiące miesiace miesiąc miesiac tygodnie
    tydzień tydzien dni lat roku rok przed ten ta to tej tego tym na do od po za przez
    dia proszę prosze powiedz przypomnij jeden dwa dwie trzy cztery pięć piec kilka
    dawno wtedy wcześniej wczesniej
    why did we when what which how the a an of to for from with and or not no
    drop dropped reject rejected choose chose decide decided ago months weeks days
    year years last about this that was were is are
    """.split()
)


def terms(question: str) -> list[str]:
    """The subject words of a question, as stems (Polish endings vary)."""
    words = re.findall(r"[\wąćęłńóśźż.+#-]+", question.lower())
    found = []
    for word in words:
        word = word.strip(".-")
        if len(word) < 2 or word in STOPWORDS:
            continue
        stem = word[: max(4, len(word) - 3)] if len(word) > 5 else word
        if stem not in found:
            found.append(stem)
    return found


def _matches(text: str, stems: list[str]) -> int:
    lowered = (text or "").lower()
    return sum(1 for stem in stems if stem in lowered)


def consequences(dia: Orchestrator, task_id: str | None) -> list[str]:
    """What came of a decided task, from the task itself and later decisions."""
    if not task_id or not (task := dia.store.get(task_id)):
        return []
    found = []
    if task.tests_ok is not None:
        found.append("tests passed" if task.tests_ok else "tests failed")
    if task.details.get("reverted_by"):
        found.append(f"rolled back later (task {task.details['reverted_by']})")
    for change in task.details.get("regression", []):
        found.append(f"made {change['metric']} worse ({change['change']:+.0%})")
    if task.details.get("incidents"):
        found.append(f"{len(task.details['incidents'])} security incident(s)")
    return found


async def why(
    dia: Orchestrator, question: str, project: str | None = None, limit: int = 8
) -> dict[str, Any]:
    """Decisions, notes and commits about the subject of ``question``."""
    stems = terms(question)
    if not stems:
        return {"terms": [], "decisions": [], "notes": [], "commits": []}
    scored = []
    for d in dia.store.decisions(project, limit=5000):
        task = dia.store.get(d["task_id"]) if d["task_id"] else None
        text = " ".join(filter(None, [d["title"], d["reason"], task.prompt if task else ""]))
        score = _matches(text, stems)
        if score:
            scored.append((score, d))
    # Most terms matched first, then the newest.
    scored.sort(key=lambda pair: (pair[0], pair[1]["at"]), reverse=True)
    decisions = []
    for _, d in scored[:limit]:
        decisions.append({**d, "consequences": consequences(dia, d["task_id"])})
    notes = []
    if dia.memory:
        try:
            for hit in dia.memory.search(" ".join(stems), limit=3):
                notes.append({"note": str(hit.path.name), "text": hit.snippet})
        except Exception:
            pass
    commits = []
    projects = [dia.config.project(project)] if project else list(dia.config.projects.values())
    for p in projects:
        args = ["log", "-i", *(f"--grep={stem}" for stem in stems)]  # any of them
        args += ["--format=%h %ad %s", "--date=short", "-n", "5"]
        try:
            out = await git(p.path, *args)
        except GitError:
            continue
        commits += [{"project": p.name, "line": line} for line in out.splitlines() if line.strip()]
    return {"terms": stems, "decisions": decisions, "notes": notes, "commits": commits[:limit]}


def describe(found: dict[str, Any]) -> str:
    if not found["terms"]:
        return "What should I look for? Name the thing (a feature, a library, a file)."
    lines = []
    for d in found["decisions"]:
        day = datetime.fromisoformat(d["at"]).astimezone().strftime("%Y-%m-%d")
        head = f"{day} {d['kind']}: {d['outcome']}  [{d['project'] or '-'}] {d['title']}"
        lines.append(head + (f" (task {d['task_id']})" if d["task_id"] else ""))
        if d["reason"] and d["kind"] != "review":
            lines.append(f"    why: {d['reason']}")
        elif d["reason"]:
            lines.append(f"    review: {d['reason'][:200]}")
        if d["consequences"]:
            lines.append(f"    then: {', '.join(d['consequences'])}")
    if found["notes"]:
        lines.append("notes:")
        lines += [f"    {n['note']}: {n['text'][:160]}" for n in found["notes"]]
    if found["commits"]:
        lines.append("commits:")
        lines += [f"    {c['project']}: {c['line']}" for c in found["commits"]]
    if not lines:
        return f"Nothing recorded about {' '.join(found['terms'])}."
    return "\n".join(lines)
