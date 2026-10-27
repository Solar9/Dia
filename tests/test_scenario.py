from pathlib import Path

from dia.brains import BrainContext, parse_intent
from dia.config import parse_config
from dia.orchestrator import Orchestrator
from dia.scenario import check_scenario


def make(tmp_path: Path, repo: Path, works: bool) -> Orchestrator:
    # The "agent" writes a test; the project's test command runs it.
    test = "exit 0" if works else "echo parry window is 0.1 s, expected 0.2 s; exit 1"
    agent = ["sh", "-c", f'echo "{test}" > test_parry.sh; echo checks the parry window']
    config = parse_config(
        {
            "dia": {"data_dir": str(tmp_path / "d"), "language": "pl", "default_agent": "a"},
            "agents": {"a": {"type": "command", "argv": agent}},
            "projects": {"nova": {"path": str(repo), "test_command": "sh test_parry.sh"}},
            "retry": {"test_fixes": 2},  # never used for scenarios
        }
    )
    return Orchestrator(config, use_memory=False)


async def test_a_scenario_that_works(tmp_path, repo) -> None:
    dia = make(tmp_path, repo, works=True)
    task = (await check_scenario(dia, "nova", "czy parry działa?")).task
    assert task.details["scenario_result"] == "works"
    assert task.summary.startswith("Tak, działa")
    assert task.branch in task.summary  # merge it to keep the test


async def test_a_scenario_that_fails_is_the_answer_not_something_to_fix(tmp_path, repo) -> None:
    dia = make(tmp_path, repo, works=False)
    task = (await check_scenario(dia, "nova", "czy parry działa?")).task
    assert task.details["scenario_result"] == "broken"
    assert task.summary.startswith("Nie działa") and "expected 0.2 s" in task.summary
    assert "retries" not in task.details


def test_the_brain_can_ask_for_a_scenario() -> None:
    ctx = BrainContext(projects={"nova": "game"}, agents=["a"])
    raw = '{"action": "scenario", "project": "nova", "prompt": "Parry in the last 0.2 s."}'
    intent = parse_intent(raw, "czy parry działa?", ctx)
    assert (intent.action, intent.project) == ("scenario", "nova")


async def test_existing_tests_that_cover_it_are_run(tmp_path, repo) -> None:
    (repo / "test_parry.sh").write_text("echo 2 passed\n")
    import subprocess

    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "tests"],
        cwd=repo,
        check=True,
    )
    dia = make(tmp_path, repo, works=True)
    dia.config.agents["a"]["argv"] = ["echo", "test_parry.sh already covers it"]
    report = await check_scenario(dia, "nova", "czy parry działa?")
    task = report.task
    assert task.commit_sha is None and task.tests_ok is True
    assert task.details["scenario_result"] == "works" and "2 passed" in report.test_output
