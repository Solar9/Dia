import subprocess
from pathlib import Path

from dia import debt
from dia.config import parse_config
from dia.orchestrator import Orchestrator

LONG = "func huge():\n" + "".join(f"\tvar x{i} = {i}\n" for i in range(70))
NESTED = "def deep():\n" + "".join("    " * (i + 1) + f"if a{i}:\n" for i in range(7))
NESTED += "    " * 8 + "pass\n"
SHARED = "".join(
    f"\tvar shared_value_{i} = compute_something_long({i}, {i * 2})\n" for i in range(8)
)


def commit(repo: Path, message: str) -> None:
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", message],
        cwd=repo,
        check=True,
    )


def make(tmp_path: Path, repo: Path) -> Orchestrator:
    files = {
        "player.gd": LONG,
        "ai.py": NESTED,
        "a.gd": "func a():\n" + SHARED,
        "b.gd": "func b():\n" + SHARED,
        "hud.gd": "func show():\n\tpass\n",
        "tested.gd": "func t():\n\tpass\n",
        "test/test_tested.gd": "func test_it():\n\ttested.t()\n",
    }
    for name, text in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text)
    commit(repo, "code")
    for i in range(4):  # the HUD and the tested script keep changing
        (repo / "hud.gd").write_text(f"func show():\n\tpass # {i}\n")
        (repo / "tested.gd").write_text(f"func t():\n\tpass # {i}\n")
        commit(repo, f"hud {i}")
    raw = {
        "dia": {"data_dir": str(tmp_path / "d"), "default_agent": "a"},
        "agents": {"a": {"type": "command", "argv": ["sh", "-c", "echo '# split' >> player.gd"]}},
        "projects": {"nova": {"path": str(repo)}},
    }
    return Orchestrator(parse_config(raw), use_memory=False)


async def test_the_register(tmp_path, repo) -> None:
    dia = make(tmp_path, repo)
    items = await debt.register(dia, "nova")
    kinds = {(i["kind"], i["file"]) for i in items}
    assert ("long function", "player.gd") in kinds
    assert ("deep nesting", "ai.py") in kinds
    assert ("duplication", "a.gd") in kinds
    assert ("no tests", "hud.gd") in kinds  # changed 5 times, no test names it
    assert ("no tests", "tested.gd") not in kinds
    assert [i["n"] for i in items] == list(range(1, len(items) + 1))
    assert items == sorted(items, key=lambda i: i["score"], reverse=True)
    assert debt.saved(dia, "nova") == items
    assert "long function: player.gd: huge() at line 1: 70 lines" in debt.describe(items)


async def test_paying_off_is_a_task(tmp_path, repo) -> None:
    dia = make(tmp_path, repo)
    items = await debt.register(dia, "nova")
    number = next(i["n"] for i in items if i["kind"] == "long function")
    report = await debt.fix(dia, "nova", number)
    assert report.task.status == "done" and report.task.details["debt"]["file"] == "player.gd"
    assert "without changing behaviour" in report.task.prompt
