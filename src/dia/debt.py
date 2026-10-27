"""Technical debt register: what to clean up first, and why.

``dia debt nova`` reads the project (nothing runs, no agent) and lists:

- **long functions** and **deep nesting** (GDScript, Python),
- **large files**,
- **duplicated code** (the same lines in two places),
- **hot code without tests** (files changed often lately that no test names),
- **vulnerable dependencies** (with ``--deps``: pip-audit / npm audit, as in
  the security report).

Each item gets a score: the benefit (how often that file changed in the last
six months: debt in code you keep touching costs you every time) times the
severity, divided by the cost (roughly, how much code a fix touches). The
register is kept, so the UI can show it; paying an item off is an ordinary
task (``dia debt nova --fix 3``, the Fix button): an agent refactors it
without changing behaviour, the tests run, you review and merge.

    [debt]
    function_lines = 60
    nesting = 5
    file_lines = 600
    duplicate_lines = 6
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dia.workspace import GitError, git

if TYPE_CHECKING:
    from dia.orchestrator import Orchestrator

SKIP = {".godot", ".import", ".git", "addons", "node_modules", ".venv", "venv", "__pycache__",
        "dist", "build"}  # fmt: skip
CODE = {".gd", ".py", ".cs", ".js", ".ts", ".rs", ".go"}
FUNC = {".gd": re.compile(r"^(\s*)(?:static\s+)?func\s+(\w+)"),
        ".py": re.compile(r"^(\s*)(?:async\s+)?def\s+(\w+)")}  # fmt: skip


def _files(root: Path) -> list[Path]:
    return sorted(
        p
        for p in root.rglob("*")
        if p.is_file()
        and p.suffix in CODE
        and not any(part in SKIP for part in p.relative_to(root).parts)
    )


def _is_test(rel: str) -> bool:
    lowered = rel.lower()
    return "test" in lowered or "spec" in Path(lowered).name


def _indent(line: str) -> int:
    expanded = line.expandtabs(4)
    return len(expanded) - len(expanded.lstrip())


def functions(text: str, suffix: str) -> list[dict[str, Any]]:
    """Functions with their length and deepest nesting (GDScript, Python)."""
    pattern = FUNC.get(suffix)
    if not pattern:
        return []
    lines = text.splitlines()
    found = []
    for i, line in enumerate(lines):
        match = pattern.match(line)
        if not match:
            continue
        base = _indent(line)
        end, depth = i + 1, 0
        while end < len(lines):
            current = lines[end]
            if current.strip() and _indent(current) <= base:
                break
            if current.strip():
                depth = max(depth, (_indent(current) - base) // 4)
            end += 1
        body = [x for x in lines[i + 1 : end] if x.strip()]
        found.append({"name": match.group(2), "line": i + 1, "lines": len(body), "depth": depth})
    return found


def _normalised(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith(("#", "//")):
            out.append(re.sub(r"\s+", " ", stripped))
    return out


def duplicates(texts: dict[str, str], window: int = 6) -> list[dict[str, Any]]:
    """Pairs of files sharing blocks of ``window`` identical (normalised) lines."""
    where: dict[str, set[str]] = defaultdict(set)
    for rel, text in texts.items():
        lines = _normalised(text)
        for i in range(len(lines) - window + 1):
            block = "\n".join(lines[i : i + window])
            if len(block) < 120:  # trivial blocks (braces, one-word lines) are no debt
                continue
            where[hashlib.sha1(block.encode()).hexdigest()].add(rel)
    pairs: Counter[tuple[str, ...]] = Counter()
    for files in where.values():
        if 1 < len(files) <= 4:
            pairs[tuple(sorted(files))] += 1
    return [
        {"files": list(files), "blocks": count}
        for files, count in pairs.most_common(20)
        if count >= 2
    ]


async def churn(root: Path, days: int = 180) -> Counter[str]:
    """How many commits touched each file lately."""
    try:
        log = await git(
            root, "log", f"--since={days} days ago", "--no-merges", "--name-only",
            "--format=tformat:",
        )  # fmt: skip
    except GitError:
        return Counter()
    return Counter(line.strip() for line in log.splitlines() if line.strip())


def _item(kind: str, file: str, detail: str, severity: float, cost: float, hot: int) -> dict:
    benefit = 1 + hot
    return {
        "kind": kind,
        "file": file,
        "detail": detail,
        "severity": severity,
        "cost": max(1.0, round(cost, 1)),
        "changes": hot,
        "score": round(benefit * severity / max(1.0, cost), 2),
    }


async def register(
    dia: Orchestrator, project_name: str, deps: bool = False
) -> list[dict[str, Any]]:
    project = dia.config.project(project_name)
    root = project.path
    opts = dia.config.section("debt")
    max_func = int(opts.get("function_lines", 60))
    max_depth = int(opts.get("nesting", 5))
    max_file = int(opts.get("file_lines", 600))
    hot = await churn(root)
    files = _files(root)
    texts = {p.relative_to(root).as_posix(): p.read_text(errors="replace") for p in files}
    items = []
    for rel, text in texts.items():
        if _is_test(rel):
            continue
        n = hot.get(rel, 0)
        size = len(text.splitlines())
        if size > max_file:
            items.append(_item("large file", rel, f"{size} lines", size / max_file, size / 200, n))
        for f in functions(text, Path(rel).suffix):
            if f["lines"] > max_func:
                detail = f"{f['name']}() at line {f['line']}: {f['lines']} lines"
                items.append(
                    _item("long function", rel, detail, f["lines"] / max_func, f["lines"] / 50, n)
                )
            elif f["depth"] > max_depth:
                detail = f"{f['name']}() at line {f['line']}: nested {f['depth']} levels"
                items.append(_item("deep nesting", rel, detail, f["depth"] / max_depth, 1, n))
    for d in duplicates(texts, int(opts.get("duplicate_lines", 6))):
        if any(_is_test(f) for f in d["files"]):
            continue
        n = max(hot.get(f, 0) for f in d["files"])
        detail = f"{d['blocks']} duplicated blocks with {', '.join(d['files'][1:])}"
        items.append(_item("duplication", d["files"][0], detail, 1 + d["blocks"] / 4, 2, n))
    tests = {rel: text.lower() for rel, text in texts.items() if _is_test(rel)}
    for rel in texts:
        if _is_test(rel) or hot.get(rel, 0) < 3:
            continue
        stem = Path(rel).stem.lower()
        if not any(re.search(rf"\b{re.escape(stem)}\b", t) for t in tests.values()):
            detail = f"changed in {hot[rel]} commits lately, no test names it"
            items.append(_item("no tests", rel, detail, 1.5, 2, hot[rel]))
    if deps:
        from dia.security import audit_dependencies

        tool, vulns = await audit_dependencies(root)
        for v in vulns if tool else []:
            detail = f"{v.package} {v.version}: {v.id}" + (
                f" (fixed in {v.fixed})" if v.fixed else ""
            )
            items.append(_item("vulnerable dependency", tool, detail, 3, 1, 0))
    items.sort(key=lambda i: i["score"], reverse=True)
    for number, item in enumerate(items, 1):
        item["n"] = number
    path = dia.config.data_dir / "debt" / f"{project.name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, indent=1))
    return items


def saved(dia: Orchestrator, project_name: str) -> list[dict[str, Any]]:
    path = dia.config.data_dir / "debt" / f"{project_name}.json"
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return []


def fix_prompt(item: dict[str, Any]) -> str:
    return (
        f"Pay off this piece of technical debt in {item['file']}: {item['kind']}, "
        f"{item['detail']}.\n\nRefactor it without changing behaviour: smaller "
        "functions, shared code instead of copies, or a test for the untested code, "
        "whichever fits. Keep the change focused on this item. The existing tests must "
        "still pass; add tests if the code had none."
    )


async def fix(dia: Orchestrator, project_name: str, number: int, on_start: Any = None) -> Any:
    items = saved(dia, project_name)
    item = next((i for i in items if i.get("n") == number), None)
    if not item:
        raise ValueError(f"no debt item {number} for {project_name}: dia debt {project_name}")
    return await dia.run_task(
        project_name, fix_prompt(item), on_start=on_start, details={"debt": item}
    )


def describe(items: list[dict[str, Any]], limit: int = 20) -> str:
    if not items:
        return "No technical debt found by the rules ([debt] in the config sets the limits)."
    lines = []
    for i in items[:limit]:
        hot = f", changed {i['changes']}x" if i["changes"] else ""
        lines.append(f"{i['n']:>3}. [{i['score']:>5}] {i['kind']}: {i['file']}: {i['detail']}{hot}")
    if len(items) > limit:
        lines.append(f"... and {len(items) - limit} more")
    return "\n".join(lines)
