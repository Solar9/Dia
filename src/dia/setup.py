"""``dia setup``: from nothing to a working Dia in a few questions.

The installer runs it at the end; you can run it again any time. It looks
around first and proposes, you confirm or change:

- **agents**: the coding CLIs you have (``claude``, ``codex``,
  ``cursor-agent``) and which one is the default;
- **projects**: git repositories under your usual folders (``~/Projekty``,
  ``~/projects``, ``~/code``, ``~/games``...), Godot projects included;
- **you**: your name, Dia's language, an Obsidian vault for memory, a
  local Ollama brain when it runs;
- **starting Dia**: the menu and desktop icons, starting at login, the
  systemd service, the KDE widget.

It writes ``~/.config/dia/config.toml`` (an existing one is kept as
``config.toml.bak``) and checks the result with ``dia doctor``. Nothing
needs root, and no package is installed: what is missing is printed with
the command for your system.
"""

from __future__ import annotations

import locale
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

AGENT_COMMANDS = [("claude", "claude-code", "claude"), ("codex", "codex", "codex"),
                  ("cursor", "cursor", "cursor-agent")]  # fmt: skip
PROJECT_ROOTS = ["Projekty", "projekty", "Projects", "projects", "code", "Code", "src",
                 "dev", "repos", "git", "games", "Games", "Godot", "workspace"]  # fmt: skip
SKIP_DIRS = {"node_modules", ".venv", "venv", ".godot", "build", "dist", "target", ".cache"}


def config_path() -> Path:
    xdg = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return xdg / "dia" / "config.toml"


@dataclass
class Answers:
    language: str = "en"
    user_name: str = ""
    agents: dict[str, str] = field(default_factory=dict)  # name -> type
    default_agent: str = ""
    projects: dict[str, Path] = field(default_factory=dict)
    vault: Path | None = None
    ollama_model: str | None = None
    crypto: bool = True


def system_language() -> str:
    lang = os.environ.get("LANG") or (locale.getlocale()[0] or "")
    return "pl" if lang.lower().startswith("pl") else "en"


def find_agents() -> dict[str, str]:
    found = {}
    for name, kind, command in AGENT_COMMANDS:
        local = Path.home() / ".local" / "bin" / command
        if shutil.which(command) or local.exists():
            found[name] = kind
    return found


def find_projects(roots: list[Path] | None = None, depth: int = 3) -> dict[str, Path]:
    """Git repositories under the usual folders (names made unique and TOML-safe)."""
    home = Path.home()
    roots = roots or [home / r for r in PROJECT_ROOTS if (home / r).is_dir()]
    found: dict[str, Path] = {}

    def walk(folder: Path, level: int) -> None:
        if (folder / ".git").exists():
            name = "".join(c if c.isalnum() or c in "-_" else "-" for c in folder.name.lower())
            name = name.strip("-") or "project"
            base, n = name, 2
            while name in found:
                name, n = f"{base}-{n}", n + 1
            found[name] = folder
            return
        if level >= depth:
            return
        try:
            children = sorted(p for p in folder.iterdir() if p.is_dir())
        except OSError:
            return
        for child in children:
            if not child.name.startswith(".") and child.name not in SKIP_DIRS:
                walk(child, level + 1)

    for root in roots:
        walk(root, 0)
    return found


def find_vault() -> Path | None:
    home = Path.home()
    for candidate in [home / "Obsidian", home / "Documents" / "Obsidian", home / "Dokumenty" /
                      "Obsidian", home / "Notes", home / "notes", home / "vault"]:  # fmt: skip
        if candidate.is_dir():
            if (candidate / ".obsidian").is_dir():
                return candidate
            for child in candidate.iterdir():
                if (child / ".obsidian").is_dir():
                    return child
    return None


def find_ollama_model() -> str | None:
    if not shutil.which("ollama"):
        return None
    out = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=10)
    names = [line.split()[0] for line in out.stdout.splitlines()[1:] if line.strip()]
    small = [n for n in names if any(s in n for s in ("3b", "1.5b", "mini", "small", "4b"))]
    return (small or names or [None])[0]


def _toml_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render(answers: Answers) -> str:
    """The config file for the answers (plain TOML, commented like the example)."""
    home = str(Path.home())

    def path(p: Path) -> str:
        text = str(p)
        return _toml_string("~" + text[len(home) :] if text.startswith(home + "/") else text)

    lines = [
        "# Dia configuration, written by `dia setup` (run it again to change it, or edit",
        "# this file; Settings in the app keep their changes in settings.json beside it).",
        "# All options: dia.example.toml in the repository.",
        "",
        "[dia]",
        f"language = {_toml_string(answers.language)}",
    ]
    if answers.default_agent:
        lines.append(f"default_agent = {_toml_string(answers.default_agent)}")
    brain = ["rules"]
    if answers.ollama_model:
        brain.append("local")
    if answers.default_agent:
        brain.append("default-agent")
    lines += [f"brain = [{', '.join(_toml_string(b) for b in brain)}]", ""]
    lines += ["[assistant]", 'name = "Dia"']
    if answers.user_name:
        lines.append(f"user_name = {_toml_string(answers.user_name)}")
    lines.append("")
    if answers.ollama_model:
        lines += ["[brains.local]", 'type = "ollama"',
                  f"model = {_toml_string(answers.ollama_model)}", ""]  # fmt: skip
    if answers.default_agent:
        lines += ["[brains.default-agent]", 'type = "agent"',
                  f"agent = {_toml_string(answers.default_agent)}", ""]  # fmt: skip
    for name, kind in answers.agents.items():
        lines += [f"[agents.{name}]", f"type = {_toml_string(kind)}", ""]
    for name, folder in answers.projects.items():
        lines += [f"[projects.{name}]", f"path = {path(folder)}", ""]
    if answers.vault:
        lines += ["[memory]", 'type = "markdown"', f"vault = {path(answers.vault)}", ""]
    if answers.crypto:
        lines += ["[skills.crypto]", 'coins = ["btc", "eth"]',
                  f'currency = "{"pln" if answers.language == "pl" else "usd"}"', ""]  # fmt: skip
    lines += ["[ui]", "enabled = true", ""]
    return "\n".join(lines)


def write(answers: Answers, target: Path | None = None) -> Path:
    target = target or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.copyfile(target, target.with_suffix(".toml.bak"))
    target.write_text(render(answers))
    return target


def missing_packages() -> list[str]:
    """What would make Dia better here, with the command to install it (not run)."""
    hints = []
    manager = next((m for m in ("pacman", "apt", "dnf", "zypper", "brew") if shutil.which(m)), "")
    install = {"pacman": "sudo pacman -S", "apt": "sudo apt install", "dnf": "sudo dnf install",
               "zypper": "sudo zypper install", "brew": "brew install"}.get(manager)  # fmt: skip
    if sys.platform.startswith("linux") and not shutil.which("bwrap"):
        hints.append(f"bubblewrap (agents in a sandbox): {install or 'install'} bubblewrap")
    if not shutil.which("git"):
        hints.append(f"git: {install or 'install'} git")
    return hints


# ------------------------------------------------------------ interaction ---


class Prompter:
    """Questions on the terminal; ``assume`` answers every one with its default."""

    def __init__(self, assume: bool = False) -> None:
        self.assume = assume or not sys.stdin.isatty()

    def ask(self, question: str, default: str = "") -> str:
        if self.assume:
            return default
        shown = f" [{default}]" if default else ""
        answer = input(f"{question}{shown}: ").strip()
        return answer or default

    def yes(self, question: str, default: bool = True) -> bool:
        if self.assume:
            return default
        answer = input(f"{question} [{'T/n' if default else 't/N'}]: ").strip().lower()
        return default if not answer else answer[0] in "ty"


MESSAGES = {
    "name": ("Jak masz na imię?", "What's your name?"),
    "agents_found": ("Znalezieni agenci: ", "Agents found: "),
    "use_agent": ("  Używać {name}?", "  Use {name}?"),
    "no_agents": (
        "Nie znalazłem claude, codex ani cursor-agent: zainstaluj któregoś "
        "i uruchom `dia setup` ponownie.",
        "No claude, codex or cursor-agent found: install one and run `dia setup` again.",
    ),
    "default_agent": ("Domyślny agent", "Default agent"),
    "repos": ("Znalezione repozytoria:", "Repositories found:"),
    "skip": ("Numery do pominięcia (np. 2 5), Enter = wszystkie",
             "Numbers to leave out (e.g. 2 5), Enter = all"),
    "extra": ("Inny folder z projektem (Enter = nie)", "Another project folder (Enter = no)"),
    "not_git": ("  to nie jest repozytorium git", "  not a git repository"),
    "vault": ("Pamięć w notatkach Obsidian: {vault}?", "Memory in the Obsidian vault {vault}?"),
    "ollama": ("Lokalny mózg z Ollamy ({model})? Darmowy i prywatny.",
               "A local brain with Ollama ({model})? Free and private."),
    "setup": ("Konfiguracja", "Setup"),
    "replace": ("{target} już jest. Zastąpić (kopia: .bak)?",
                "{target} exists. Replace it (backup: .bak)?"),
    "kept": ("Zostawiam konfigurację bez zmian.", "Keeping the configuration."),
    "written": ("Zapisano: {target}", "Written: {target}"),
    "icon": ("Ikona Dia w menu i na pulpicie?", "Dia's icon in the menu and on the desktop?"),
    "autostart": ("Uruchamiać Dia przy logowaniu?", "Start Dia at login?"),
    "service": ("Dia jako usługa systemd (w tle, restart po awarii)?",
                "Dia as a systemd user service (in the background, restarts on failure)?"),
    "widget": ("Widżet Dia na panelu KDE?", "Dia's widget for the KDE panel?"),
    "worth": ("Warto doinstalować: ", "Worth installing: "),
    "done": ("Gotowe. Dia startuje ikoną albo poleceniem `dia up`.",
             "Done. Start Dia with its icon or `dia up`."),
}  # fmt: skip


def interview(prompt: Prompter, pl: bool) -> Answers:
    def t(key: str, **values: Any) -> str:
        return MESSAGES[key][0 if pl else 1].format(**values)

    answers = Answers(language="pl" if pl else "en")
    answers.user_name = prompt.ask(t("name"), os.environ.get("USER", "").capitalize())
    found = find_agents()
    if found:
        print(t("agents_found") + ", ".join(found))
        answers.agents = {n: k for n, k in found.items() if prompt.yes(t("use_agent", name=n))}
    else:
        print(t("no_agents"))
    if answers.agents:
        first = next(iter(answers.agents))
        choice = prompt.ask(t("default_agent"), first)
        answers.default_agent = choice if choice in answers.agents else first
    projects = find_projects()
    if projects:
        print(t("repos"))
        for i, (name, folder) in enumerate(projects.items(), 1):
            print(f"  {i:>2}. {name:<20} {folder}")
        skip = prompt.ask(t("skip"), "")
        drop = {int(n) for n in skip.replace(",", " ").split() if n.isdigit()}
        answers.projects = {n: p for i, (n, p) in enumerate(projects.items(), 1) if i not in drop}
    while extra := prompt.ask(t("extra")):
        folder = Path(extra).expanduser().resolve()
        if (folder / ".git").exists():
            for name, path in find_projects([folder], depth=0).items():
                answers.projects.setdefault(name, path)
        else:
            print(t("not_git"))
    vault = find_vault()
    if vault and prompt.yes(t("vault", vault=vault)):
        answers.vault = vault
    model = find_ollama_model()
    if model and prompt.yes(t("ollama", model=model)):
        answers.ollama_model = model
    return answers


def run(assume: bool = False, target: Path | None = None) -> int:
    """The whole wizard: questions, config, shortcuts, service, check."""
    from dia import __version__, desktop
    from dia.banner import banner

    pl = system_language() == "pl"

    def t(key: str, **values: Any) -> str:
        return MESSAGES[key][0 if pl else 1].format(**values)

    print(banner([f"Dia {__version__}", t("setup")]))
    print()
    prompt = Prompter(assume)
    target = target or config_path()
    if target.exists() and not prompt.yes(t("replace", target=target), default=False):
        print(t("kept"))
    else:
        print(t("written", target=write(interview(prompt, pl), target)))
    if prompt.yes(t("icon")):
        autostart = prompt.yes(t("autostart"), default=False)
        for line in desktop.install(target, desktop=True, autostart=autostart):
            print(f"  {line}")
    linux = sys.platform.startswith("linux")
    if linux and shutil.which("systemctl") and prompt.yes(t("service"), default=False):
        from dia import service

        for line in service.install(target):
            print(f"  {line}")
    if shutil.which("kpackagetool6") and prompt.yes(t("widget"), default=False):
        from dia.ui import plasmoid_install

        try:
            print("  " + plasmoid_install.install())
        except RuntimeError as exc:
            print(f"  {exc}")
    for hint in missing_packages():
        print(t("worth") + hint)
    print()
    doctor = subprocess.run([sys.executable, "-m", "dia", "--config", str(target), "doctor"])
    print()
    print(t("done"))
    return 0 if doctor.returncode == 0 else 1


def answers_from(**values: Any) -> Answers:
    """For tests and scripted installs."""
    return Answers(**values)
