import subprocess
from pathlib import Path

import pytest

from dia.config import parse_config
from dia.orchestrator import Orchestrator, TaskActionError
from dia.quality import blockers, parse_assumptions, parse_violations, static_violations


def layered(repo: Path) -> None:
    (repo / "ui").mkdir()
    (repo / "data").mkdir()
    (repo / "data" / "store.py").write_text("def load(): ...\n")
    (repo / "ui" / "menu.py").write_text("def show(): ...\n")
    (repo / "ARCHITECTURE.md").write_text("- UI never talks to the data layer directly.\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "layers"],
        cwd=repo,
        check=True,
    )


FORBID = [{"from": "ui/**", "to": "data/**", "why": "UI never talks to the data layer"}]


def make(tmp_path: Path, repo: Path, script: str, **project) -> Orchestrator:
    raw = {
        "dia": {"data_dir": str(tmp_path / "d"), "default_agent": "a"},
        "agents": {
            "a": {"type": "command", "argv": ["sh", "-c", script, "{prompt}"]},
            # the reviewer reports the broken rule
            "r": {
                "type": "command",
                "argv": [
                    "sh",
                    "-c",
                    "echo 'VERDICT: CHANGES_REQUESTED'; "
                    "echo 'VIOLATION: UI never talks to the data layer: ui/menu.py imports store'",
                ],
            },
        },
        "projects": {"demo": {"path": str(repo), "architecture_forbid": FORBID, **project}},
    }
    return Orchestrator(parse_config(raw), use_memory=False)


def test_static_check(repo) -> None:
    layered(repo)
    (repo / "ui" / "menu.py").write_text("import store\n")
    found = static_violations(repo, ["ui/menu.py", "data/store.py"], FORBID)
    assert found == [
        {"rule": "UI never talks to the data layer", "where": "ui/menu.py uses data/store.py",
         "by": "static"}
    ]  # fmt: skip
    assert static_violations(repo, ["data/store.py"], FORBID) == []


def test_parsing() -> None:
    text = "VERDICT: CHANGES_REQUESTED\n- VIOLATION: no globals: player.gd adds one\nother"
    assert parse_violations(text) == [
        {"rule": "no globals", "where": "player.gd adds one", "by": "review"}
    ]
    answer = 'ok {"assumptions": [{"assumption": "a", "check": "true"}, {"assumption": "b"}]}'
    assert parse_assumptions(answer) == [{"assumption": "a", "check": "true"}]


async def test_a_violation_blocks_the_merge_until_overridden(tmp_path, repo) -> None:
    layered(repo)
    dia = make(tmp_path, repo, "echo 'import store' > ui/menu.py; echo done")
    task = (await dia.run_task("demo", "show saves in the menu")).task
    assert task.status == "done"
    assert task.details["violations"][0]["where"] == "ui/menu.py uses data/store.py"
    with pytest.raises(TaskActionError, match="blocked by the quality guards"):
        await dia.merge_task(task.id)
    await dia.merge_task(task.id, override="the menu only reads, agreed with myself")
    kinds = [d["kind"] for d in dia.store.decisions("demo")]
    assert kinds == ["merge", "override"]


async def test_the_reviewer_checks_the_prose_rules(tmp_path, repo) -> None:
    layered(repo)
    dia = make(tmp_path, repo, "echo '# fine' >> ui/menu.py; echo done")
    task = (await dia.run_task("demo", "tidy the menu")).task
    assert "violations" not in task.details
    await dia.review_task(task.id, "r", fix_rounds=0)
    task = dia.store.get(task.id)
    assert task.details["violations"][0]["by"] == "review"
    assert blockers(task) == [
        "architecture: UI never talks to the data layer (ui/menu.py imports store)"
    ]


async def test_assumptions_are_checked_not_believed(tmp_path, repo) -> None:
    layered(repo)
    # The agent edits, then (asked read-only) states two assumptions: one true, one false.
    script = (
        'case "$0" in *assumptions*) echo \'{"assumptions": ['
        '{"assumption": "store.py has load()", "check": "grep -q \\"def load\\" data/store.py"},'
        '{"assumption": "there is a save() too", "check": "grep -q \\"def save\\" data/store.py"}'
        "]}' ;; *) echo '# changed' >> data/store.py; echo done ;; esac"
    )
    dia = make(tmp_path, repo, script, verification={"always": True})
    task = (await dia.run_task("demo", "speed up loading")).task
    verification = task.details["verification"]
    assert (verification["held"], verification["total"]) == (1, 2)
    assert [c["held"] for c in verification["checks"]] == [True, False]
    assert blockers(task) == [
        'assumption failed: there is a save() too (grep -q "def save" data/store.py)'
    ]
    with pytest.raises(TaskActionError):
        await dia.merge_task(task.id)


async def test_small_changes_skip_the_gate(tmp_path, repo) -> None:
    layered(repo)
    dia = make(tmp_path, repo, "echo '# x' >> data/store.py; echo done")
    task = (await dia.run_task("demo", "comment")).task
    assert "verification" not in task.details and blockers(task) == []
