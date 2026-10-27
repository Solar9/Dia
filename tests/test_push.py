import json
from pathlib import Path

import pytest

pytest.importorskip("pywebpush")

from dia import push as push_module  # noqa: E402
from dia.config import parse_config  # noqa: E402
from dia.orchestrator import Event, Orchestrator  # noqa: E402
from dia.push import Push  # noqa: E402
from dia.store import TaskRecord  # noqa: E402

SUB = {"endpoint": "https://push.example/abc", "keys": {"p256dh": "k", "auth": "a"}}


@pytest.fixture
def push(tmp_path: Path, monkeypatch) -> tuple[Push, list]:
    dia = Orchestrator(parse_config({"dia": {"data_dir": str(tmp_path)}}), use_memory=False)
    sent = []

    def fake(self, sub, payload):
        sent.append((sub["device"], json.loads(payload)))
        return sub["endpoint"] != "https://push.example/gone"

    monkeypatch.setattr(push_module.Push, "_send_one", fake)
    return Push(dia), sent


async def test_keys_subscriptions_and_events(push) -> None:
    p, sent = push
    key = p.public_key()
    assert len(key) == 87 and p.public_key() == key  # 65 bytes, stable
    assert p.key_path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError):
        p.subscribe({"endpoint": "http://insecure"}, None)
    p.subscribe(SUB, "phone")
    p.subscribe(SUB, "phone")  # same endpoint: replaced
    p.subscribe({**SUB, "endpoint": "https://push.example/gone"}, "old")
    assert await p.send("t", "b") == 1
    assert [s["device"] for s in p.subscriptions()] == ["phone"]  # 410 → dropped

    task = TaskRecord(id="t1", project="nova", agent="claude", mode="edit", prompt="fix x")
    await p.on_event(Event("ci", task, "failed"))
    assert sent[-1][1]["title"] == "CI · nova" and sent[-1][1]["url"] == "/#task=t1"
    await p.on_event(Event("voice", None, "listening"))
    assert len(sent) == 3

    for status in ("queued", "running", "done", "done"):
        task.status = status
        p.on_task_saved(task)
    await p.dia.drain()
    assert len(sent) == 4 and sent[-1][1]["title"].startswith("✅ nova: fix x")

    p.forget_device("phone")
    assert p.subscriptions() == []
