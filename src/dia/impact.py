"""What could break if I change this? "Co się może zepsuć, jeśli zmienię dash?"

Three kinds of evidence, all read from the project, nothing run:

- **dependencies**: in a Godot project, which scenes, scripts and resources
  use what (``ext_resource`` paths, ``preload``/``load``, ``extends``, a
  ``class_name`` used by name, autoloads). In any project, files that
  mention the changed file's name. Followed backwards a few steps: what
  uses what uses it.
- **history**: files that changed in the same commits as the target, often
  enough to be a habit ("player.gd and hud.gd change together in 7 of 9
  commits"), even when no reference connects them.
- **tests**: test files among those, and tests that name the target.

The target can be a path, a file name, or a word (``dash``): it matches
file names, ``func dash``/``class_name``, and node names in scenes.
``dia impact nova dash`` prints it; ``--agent`` hands it to an agent that
reads the code and says what is likely to break and what to test.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dia.workspace import GitError, git

if TYPE_CHECKING:
    from dia.orchestrator import Orchestrator

SKIP = {".godot", ".import", ".git", "addons", "node_modules", ".venv", "venv", "__pycache__"}
SOURCES = {".gd", ".tscn", ".tres", ".gdshader", ".cs", ".py", ".js", ".ts", ".rs", ".go"}
RES = re.compile(r'res://([^"\')\s]+)')
CLASS_NAME = re.compile(r"^class_name\s+(\w+)", re.M)
AUTOLOAD = re.compile(r'^(\w+)="\*?res://([^"]+)"', re.M)
MAX_FILES = 5000


@dataclass
class Impact:
    query: str
    targets: list[str] = field(default_factory=list)
    dependents: list[dict[str, Any]] = field(default_factory=list)  # file, via, depth
    cochanged: list[dict[str, Any]] = field(default_factory=list)  # file, together, of
    tests: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _files(root: Path) -> list[Path]:
    found = []
    for path in root.rglob("*"):
        if any(part in SKIP for part in path.relative_to(root).parts):
            continue
        if path.is_file() and path.suffix.lower() in SOURCES:
            found.append(path)
            if len(found) >= MAX_FILES:
                break
    return sorted(found)


def _read(path: Path) -> str:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""


def graph(root: Path) -> dict[str, set[str]]:
    """file -> the files it uses (paths relative to ``root``)."""
    files = _files(root)
    texts = {f.relative_to(root).as_posix(): _read(f) for f in files}
    uses: dict[str, set[str]] = defaultdict(set)
    # Names that stand for a file: class_name declarations and autoloads.
    names: dict[str, str] = {}
    for rel, text in texts.items():
        if rel.endswith(".gd") and (m := CLASS_NAME.search(text)):
            names[m.group(1)] = rel
    project_file = root / "project.godot"
    if project_file.is_file():
        for name, path in AUTOLOAD.findall(_read(project_file)):
            names[name] = path
    stems: dict[str, set[str]] = defaultdict(set)
    for rel in texts:
        stems[Path(rel).stem].add(rel)
    word = re.compile(r"\b(" + "|".join(map(re.escape, names)) + r")\b") if names else None
    for rel, text in texts.items():
        for target in RES.findall(text):
            if target != rel and (target in texts or (root / target).exists()):
                uses[rel].add(target)
        if word and rel.endswith(".gd"):
            for name in set(word.findall(text)):
                if names[name] != rel:
                    uses[rel].add(names[name])
        if not rel.endswith((".gd", ".tscn", ".tres", ".gdshader")):
            # Elsewhere: a module or file mentioned by name (import x, require("./x")).
            for token in set(re.findall(r"[A-Za-z_][\w-]{2,}", text)):
                for other in stems.get(token, ()):
                    if other != rel:
                        uses[rel].add(other)
    return uses


def find_targets(root: Path, query: str) -> list[str]:
    """Files the query names: a path, a file name, or a word in names and code."""
    query = query.strip().removeprefix("res://")
    if (root / query).is_file():
        return [query]
    word = query.lower()
    by_name, by_code = [], []
    name = re.escape(word)
    func = re.compile(rf"^(?:static\s+)?func\s+_?{name}\b|^class_name\s+{name}\b", re.M | re.I)
    node = re.compile(rf'^\[node name="{name}"', re.M | re.I)
    for path in _files(root):
        rel = path.relative_to(root).as_posix()
        if word in Path(rel).stem.lower():
            by_name.append(rel)
        elif path.suffix in (".gd", ".tscn") and (
            func.search(text := _read(path)) or node.search(text)
        ):
            by_code.append(rel)
    found = by_name + by_code
    # Tests of the thing are reported as tests, not as the thing itself.
    return ([f for f in found if not _is_test(f)] or found)[:10]


def dependents(uses: dict[str, set[str]], targets: list[str], depth: int = 3) -> list[dict]:
    used_by: dict[str, set[str]] = defaultdict(set)
    for user, used in uses.items():
        for target in used:
            used_by[target].add(user)
    seen = set(targets)
    found = []
    frontier = [(t, t) for t in targets]
    for level in range(1, depth + 1):
        following = []
        for target, _ in frontier:
            for user in sorted(used_by.get(target, ())):
                if user not in seen:
                    seen.add(user)
                    found.append({"file": user, "via": target, "depth": level})
                    following.append((user, target))
        frontier = following
    return found


async def cochanged(root: Path, targets: list[str], commits: int = 500) -> list[dict]:
    try:
        log = await git(
            root, "log", f"-n{commits}", "--no-merges", "--name-only", "--format=tformat:@@"
        )
    except GitError:
        return []
    together: Counter[str] = Counter()
    total = 0
    for chunk in log.split("@@"):
        changed = {line.strip() for line in chunk.splitlines() if line.strip()}
        if changed & set(targets):
            total += 1
            together.update(changed - set(targets))
    return [
        {"file": f, "together": n, "of": total}
        for f, n in together.most_common(10)
        if n >= 2 and n / total >= 0.3
    ]


def _is_test(path: str) -> bool:
    lowered = path.lower()
    return "test" in lowered or "spec" in Path(lowered).name


async def analyze(root: Path, query: str) -> Impact:
    result = Impact(query=query, targets=find_targets(root, query))
    if not result.targets:
        return result
    uses = graph(root)
    result.dependents = dependents(uses, result.targets)
    result.cochanged = await cochanged(root, result.targets)
    tests = {d["file"] for d in result.dependents if _is_test(d["file"])}
    tests |= {c["file"] for c in result.cochanged if _is_test(c["file"])}
    stems = {Path(t).stem.lower() for t in result.targets} | {query.lower()}
    for path in _files(root):
        rel = path.relative_to(root).as_posix()
        if _is_test(rel) and rel not in result.targets:
            text = _read(path).lower()
            if any(re.search(rf"\b{re.escape(s)}\b", text) for s in stems):
                tests.add(rel)
    result.tests = sorted(tests)
    return result


def describe(result: Impact) -> str:
    if not result.targets:
        return f"Nothing in the project matches '{result.query}' (a path, file name or function)."
    lines = [f"{result.query}: {', '.join(result.targets)}"]
    if result.dependents:
        lines.append("uses it (directly or through others):")
        for d in result.dependents[:25]:
            via = "" if d["depth"] == 1 else f"  (via {d['via']})"
            lines.append(f"  {d['file']}{via}")
    else:
        lines.append("nothing refers to it")
    if result.cochanged:
        lines.append("usually changes together with it:")
        lines += [
            f"  {c['file']}  ({c['together']} of {c['of']} commits)" for c in result.cochanged
        ]
    lines.append(
        "tests: " + (", ".join(result.tests) if result.tests else "none found: worth adding one")
    )
    return "\n".join(lines)


ADVICE = """\
I want to change "{query}" in this project. Here is what refers to it and \
what changes with it:

{report}

Read the relevant code and tell me, briefly: what is most likely to break \
and why, what I should test by hand, and which existing tests cover it. \
Change no files."""


async def impact(
    dia: Orchestrator, project_name: str, query: str, advise: bool = False
) -> tuple[Impact, str]:
    project = dia.config.project(project_name)
    result = await analyze(project.path, query)
    text = describe(result)
    if advise and result.targets:
        from dia.agents import Mode

        report = await dia.run_task(
            project.name, ADVICE.format(query=query, report=text), mode=Mode.READ_ONLY
        )
        text += "\n\n" + (report.task.summary or report.task.error or "")
    return result, text
