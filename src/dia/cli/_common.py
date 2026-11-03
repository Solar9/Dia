"""Helpers shared by several command modules."""

from __future__ import annotations

import sys

from dia.cli.serve import _ui_url
from dia.core.config import Config
from dia.core.orchestrator import Orchestrator, TaskReport
from dia.core.store import TaskRecord


async def finish_learning(dia: Orchestrator, task_id: str) -> None:
    """Wait for the fact proposals of `[memory] learn` and show them."""
    if not dia.learning:
        return
    print("learning from the task ...", file=sys.stderr)
    await dia.drain()
    task = dia.store.get(task_id)
    if task and any(f["status"] == "proposed" for f in task.details.get("learn", [])):
        print_facts(task)


def print_facts(task: TaskRecord) -> None:
    print(f"\nworth remembering about {task.project} (task {task.id}):")
    for i, item in enumerate(task.details.get("learn", []), 1):
        if item["status"] == "proposed":
            print(f"  {i}. {item['fact']}")
    print(f"  accept: dia learned {task.id} --accept 1 2 ... | all; reject: --reject all")


def _call_serve(config: Config, method: str, path: str) -> dict | None:
    """Call the running `dia serve` on this computer; None when it isn't running."""
    import json
    import urllib.error
    import urllib.request

    url, token = _ui_url(config)
    req = urllib.request.Request(
        url.rstrip("/") + path, method=method, headers={"Authorization": f"Bearer {token}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, OSError):
        return None


def skill_args(skill_args: dict[str, str], words: list[str]) -> dict[str, str]:
    """``place=Gdańsk`` pairs; bare words go to the skill's first argument."""
    found: dict[str, str] = {}
    loose = []
    for word in words:
        key, eq, value = word.partition("=")
        if eq and key in skill_args:
            found[key] = value
        else:
            loose.append(word)
    if loose and skill_args:
        first = next(iter(skill_args))
        found[first] = " ".join(filter(None, [found.get(first, ""), *loose]))
    return found


def print_report(report: TaskReport) -> None:
    task = report.task
    for warning in report.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    print(f"task:    {task.id}  [{task.status}]  agent={task.agent}")
    if task.commit_sha:
        print(f"branch:  {task.branch} @ {task.commit_sha[:10]}")
        print(report.diff_stat)
    if task.tests_ok is not None:
        summary = report.test_output.splitlines()[0] if report.test_output else ""
        print(f"tests:   {'passed' if task.tests_ok else 'FAILED'}  {summary}".rstrip())
        if not task.tests_ok:
            print(report.test_output[-3000:])
        print(f"         full log: dia show {task.id} --tests")
    for step in task.details.get("steps", []):
        mark = "ok" if step["success"] else "FAILED"
        print(f"step:    {step['title']} [{step['agent']}] {mark} ({step['duration_s']}s)")
    if task.summary:
        print("\n" + task.summary)
    for review in task.details.get("reviews", []):
        print(f"\nreview (round {review['round']}) by {review['reviewer']}: {review['verdict']}")
        print(review["findings"])
        if reply := review.get("author_reply"):
            print(f"\n{task.agent} replied: {reply}")
    if task.error:
        print(f"\nerror: {task.error}", file=sys.stderr)
