import subprocess
from pathlib import Path

from dia.config import parse_config
from dia.orchestrator import Orchestrator


def make(tmp_path: Path, repo: Path, agents: dict, retry: dict, test_command: str | None = None):
    project = {"path": str(repo), **({"test_command": test_command} if test_command else {})}
    config = parse_config(
        {
            "dia": {"data_dir": str(tmp_path / "data"), "default_agent": next(iter(agents))},
            "agents": {n: {"type": "command", "argv": a} for n, a in agents.items()},
            "projects": {"demo": project},
            "retry": retry,
        }
    )
    return Orchestrator(config, use_memory=False)


def committed(repo: Path, branch: str) -> list[str]:
    out = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", branch], cwd=repo, capture_output=True, text=True
    )
    return out.stdout.split()


async def test_a_failed_attempt_is_tried_again_and_its_mess_dropped(tmp_path, repo) -> None:
    marker = tmp_path / "tried-once"
    flaky = [
        "sh",
        "-c",
        f'if [ -f "{marker}" ]; then echo ok > ok.txt; echo done; '
        f'else touch "{marker}"; echo half > junk.txt; exit 1; fi',
    ]
    orch = make(tmp_path, repo, {"flaky": flaky}, {"agent_errors": 1})
    task = (await orch.run_task("demo", "add ok.txt")).task
    assert task.status == "done", task.error
    assert [r["kind"] for r in task.details["retries"]] == ["agent"]
    files = committed(repo, task.branch)
    assert "ok.txt" in files and "junk.txt" not in files


async def test_without_a_policy_a_failure_is_final(tmp_path, repo) -> None:
    orch = make(tmp_path, repo, {"bad": ["sh", "-c", "exit 1"]}, {})
    task = (await orch.run_task("demo", "anything")).task
    assert task.status == "failed" and "retries" not in task.details


async def test_another_agent_takes_over(tmp_path, repo) -> None:
    agents = {
        "bad": ["sh", "-c", "exit 1"],
        "good": ["sh", "-c", "echo hi > hi.txt; echo did it"],
    }
    orch = make(tmp_path, repo, agents, {"agent_errors": 1, "switch_agent": True})
    task = (await orch.run_task("demo", "say hi")).task
    assert task.status == "done", task.error
    assert task.details["author"] == "good"
    assert task.details["retries"][0] == {
        "kind": "agent",
        "agent": "bad",
        "next": "good",
        "error": task.details["retries"][0]["error"],
    }


async def test_failed_tests_go_back_to_the_author(tmp_path, repo) -> None:
    agent = [
        "sh",
        "-c",
        'case "$0" in *test-output*) echo fixed > x.txt;; *) echo broken > x.txt;; esac',
        "{prompt}",
    ]
    orch = make(tmp_path, repo, {"a": agent}, {"test_fixes": 2}, "grep -q fixed x.txt")
    task = (await orch.run_task("demo", "write x")).task
    assert task.status == "done" and task.tests_ok is True, task.error
    assert task.details["retries"] == [{"kind": "tests", "agent": "a", "round": 1}]

    orch = make(tmp_path, repo, {"a": agent}, {}, "grep -q fixed x.txt")
    assert (await orch.run_task("demo", "write x")).task.tests_ok is False


async def test_a_project_overrides_the_policy(tmp_path, repo) -> None:
    from dia.retry import RetryPolicy

    orch = make(tmp_path, repo, {"a": ["true"]}, {"agent_errors": 1, "test_fixes": 1})
    project = orch.config.project("demo")
    project.options["retry"] = {"test_fixes": 3}
    policy = RetryPolicy.for_project(orch.config, project)
    assert (policy.agent_errors, policy.test_fixes) == (1, 3)
