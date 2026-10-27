import subprocess
from pathlib import Path

from dia import profile
from dia.config import parse_config
from dia.orchestrator import Orchestrator

DRAFT = "Here is the profile:\n## Accepts\n- Small changes\n## Rejects\n- Rewrites\n"


def make(tmp_path: Path, repo: Path) -> Orchestrator:
    # The drafting agent records what it was shown and answers with a profile.
    seen = tmp_path / "seen.txt"
    raw = {
        "dia": {"data_dir": str(tmp_path / "d"), "default_agent": "a"},
        "agents": {
            "a": {"type": "command", "argv": ["sh", "-c", "echo x >> inv.gd; echo done"]},
            "writer": {
                "type": "command",
                "argv": ["sh", "-c", f'printf "%s" "$0" > {seen}; printf "{DRAFT}"', "{prompt}"],
            },
        },
        "projects": {"nova": {"path": str(repo)}},
        "profile": {"agent": "writer"},
    }
    return Orchestrator(parse_config(raw), use_memory=False)


async def test_profile_from_decisions_waits_for_approval(tmp_path, repo) -> None:
    dia = make(tmp_path, repo)
    task = (await dia.run_task("nova", "Rewrite the inventory")).task
    await dia.discard_task(task.id, "too big, I want small steps")
    task = (await dia.run_task("nova", "Fix the inventory sort")).task
    await dia.merge_task(task.id)
    # ... and then the user fixed the agent's work by hand
    (repo / "inv.gd").write_text("fixed\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.name=me", "-c", "user.email=me@x", "commit", "-qm", "Use typed arrays"],
        cwd=repo,
        check=True,
    )
    draft = await profile.update(dia)
    assert draft.startswith("## Accepts") and profile.read(dia) == ""  # not yet the profile
    shown = (tmp_path / "seen.txt").read_text()
    assert "their reason: too big, I want small steps" in shown
    assert "they then fixed it themselves: Use typed arrays" in shown

    profile.accept(dia)
    assert "- Small changes" in profile.read(dia) and profile.proposal(dia) == ""
    # agents get it with every task
    assert "How the user works" in dia._context(dia.config.project("nova"), "x")
    assert "- Rewrites" in dia._context(dia.config.project("nova"), "x")
