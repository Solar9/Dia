"""`dia voice` commands."""

from __future__ import annotations

import argparse
import asyncio
import sys

from dia.core.config import Config, ConfigError
from dia.core.orchestrator import Orchestrator


async def cmd_say(config: Config, args: argparse.Namespace) -> int:
    """Talk to Dia in your own words; a brain decides what to do."""
    from dia.assistant import Assistant

    dia = Orchestrator(config, use_memory=not args.no_memory)
    assistant = Assistant(dia, config.brain_chain(only=args.brain))
    intent = await assistant.interpret(args.text)
    target = f" project={intent.project}" if intent.project else ""
    print(f"[{intent.brain or '-'}] {intent.action}{target}", file=sys.stderr)
    if understood := assistant.understood(intent):
        print(f"understood: {understood}", file=sys.stderr)
    if intent.reply:
        print(intent.reply)
    if args.dry_run:
        if intent.prompt and intent.action in ("run", "ask"):
            print(f"prompt: {intent.prompt}")
        return 0
    response = await assistant.execute(intent)
    if intent.action == "plan" and assistant.pending_plan:
        print(response.text)
        answer = "y" if args.yes else input("[y/N] ").strip().lower()
        if answer not in ("y", "yes", "t", "tak"):
            print(f"not started; run it later with: dia plan --start {assistant.pending_plan}")
            return 0
        response = await assistant.execute(await assistant.interpret("yes"))
    if response.report:
        task = response.report.task
        print(f"task:    {task.id}  [{task.status}]  agent={task.agent}")
        if task.commit_sha:
            print(f"branch:  {task.branch}  (dia diff / merge / discard {task.id})")
    if response.text and response.text != intent.reply:
        print("\n" + response.text)
    return 0 if not response.report or response.report.task.status == "done" else 1


def _voice_channel(config: Config):
    name = next((n for n, o in config.channels.items() if o.get("type", n) == "voice"), None)
    if not name:
        raise ConfigError("no voice channel configured; add [channels.voice] (see docs/VOICE.md)")
    return config.channel(name, Orchestrator(config, use_memory=False))


async def _speakers(config: Config, args: argparse.Namespace) -> int:
    """Enroll, list or forget the voices Dia recognises."""
    from dia.voice.audio import is_silent
    from dia.voice.speaker import read_samples

    voice = _voice_channel(config)
    if not voice.speakers:
        print("speaker recognition is off: set [channels.voice] speaker", file=sys.stderr)
        return 2
    if args.action == "speakers":
        print("\n".join(voice.speakers.names()) or "nobody enrolled yet")
        return 0
    if not args.text:
        print(f"usage: dia voice {args.action} NAME", file=sys.stderr)
        return 2
    if args.action == "forget":
        found = voice.speakers.forget(args.text)
        print("forgotten" if found else f"no speaker {args.text}")
        return 0 if found else 1
    if problem := voice.speakers.check() or voice.recorder.check():
        print(f"voice: {problem}", file=sys.stderr)
        return 2
    samples = []
    for n in range(1, 4):
        path = voice._tmp / f"enroll-{n}.wav"
        input(f"[{n}/3] press Enter, then speak naturally for {args.seconds:g} s...")
        await voice.recorder.start(path)
        await asyncio.sleep(args.seconds)
        await voice.recorder.stop()
        if is_silent(path):
            print("only silence was recorded; check the microphone", file=sys.stderr)
            return 1
        samples.append(read_samples(path))
        path.unlink(missing_ok=True)
    count = voice.speakers.enroll(args.text, samples)
    print(f"{args.text}: {count} voice samples kept (as numbers, not recordings)")
    return 0


async def cmd_voice(config: Config, args: argparse.Namespace) -> int:
    """Control the running voice channel, or test the microphone and voice."""
    from dia.channels.voice import send_command

    if args.action == "speak":
        voice = _voice_channel(config)
        await voice.say(args.text or "Cześć, tu Dia. Słyszysz mnie?")
        return 0
    if args.action in ("enroll", "speakers", "forget"):
        return await _speakers(config, args)
    if args.action == "listen":
        voice = _voice_channel(config)
        if problem := voice.check():
            print(f"voice: {problem}", file=sys.stderr)
            return 2
        path = voice._tmp / "test.wav"
        print(f"recording {args.seconds}s, speak now...", file=sys.stderr)
        await voice.recorder.start(path)
        await asyncio.sleep(args.seconds)
        await voice.recorder.stop()
        from dia.voice.audio import is_silent

        if is_silent(path):
            print(
                "the recording is silent: the microphone is muted or the wrong input is "
                "selected (check your sound settings)",
                file=sys.stderr,
            )
            return 1
        print("transcribing (the first run downloads the model)...", file=sys.stderr)
        print(await voice.stt.transcribe(path, voice.language) or "(nothing heard)")
        return 0
    try:
        print(await send_command(args.action))
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def add_say(sub: argparse._SubParsersAction) -> None:
    say = sub.add_parser("say", help="ask or tell Dia something in your own words")
    say.add_argument("text")
    say.add_argument("-b", "--brain", help="use only this brain (default: the configured chain)")
    say.add_argument("--dry-run", action="store_true", help="only show how it was understood")
    say.add_argument("--no-memory", action="store_true", help="don't use or update memory")
    say.add_argument("-y", "--yes", action="store_true", help="run a proposed plan without asking")
    say.set_defaults(fn=cmd_say)


def add_voice(sub: argparse._SubParsersAction) -> None:
    voice = sub.add_parser("voice", help="voice control (bind `dia voice toggle` to a shortcut)")
    voice.add_argument(
        "action",
        choices=[
            "toggle",
            "start",
            "stop",
            "cancel",
            "ping",
            "listen",
            "speak",
            "enroll",
            "speakers",
            "forget",
        ],
        help="toggle/start/stop/cancel/ping control `dia serve`; listen/speak test mic and "
        "voice; enroll/speakers/forget manage the voices Dia recognises",
    )
    voice.add_argument("text", nargs="?", help="speak: what to say; enroll/forget: the name")
    voice.add_argument("-s", "--seconds", type=float, default=5, help="listen: how long to record")
    voice.set_defaults(fn=cmd_voice)


COMMANDS = {
    "say": add_say,
    "voice": add_voice,
}
