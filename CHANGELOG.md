# Changelog

All notable changes to Dia. Versions follow [Semantic Versioning](https://semver.org/);
before 1.0 a minor version may change the configuration.

## [Unreleased]

## [0.1.0] — 2026-10-27

The first public release, under the PolyForm Noncommercial License 1.0.0;
commercial use needs a license, see `COMMERCIAL-LICENSE.md`. It contains
everything built during private development, listed below.

## Before the first public release

These versions were private development builds. Their numbers (0.0.1 to
0.0.5) were internal; the first public release is 0.1.0 and includes all of
this.

### Private build 0.0.5 — 2026-10-27

#### Added
- Take over a terminal CLI session and continue its conversation in the app;
  release it to resume in a terminal later.

#### Changed
- CLI sessions have their own tab, with a conversation viewer for Claude Code,
  Codex and Cursor Agent.

#### Fixed
- Count daily suggestions by the local calendar day of their stored UTC timestamp.
- Refresh tray service status independently of the HTTP status request.
- Run the session take-over test stub outside the agent sandbox.

Validation: 384 tests passed on the preceding implementation commit `fa402ad`.

### Private build 0.0.4 — 2026-10-27

#### Added
- Choose a model per agent (Settings → Agents): a suggestion list per CLI, any
  other name can be typed, empty means auto (the CLI's own default).
- A model can be chosen per task next to the agent in the task form
  (`model` in `POST /api/tasks`); it applies only to the agent it was chosen for.
- Anywhere an agent is named, `agent:model` (e.g. `claude:opus`) runs it with that model
  for that use: scenarios, plans (planner), research, experiments, debugging, council
  members and the settings' agent lists. The dashboard forms have the pickers.
- The dashboard lists agent CLI sessions running on the computer (Claude Code,
  Codex, Cursor), including those started by hand outside Dia
  (`GET /api/cli-sessions`).

#### Changed
- Dia's name is never inflected in Polish texts: always "Dia", not "Dii", "Dię", "Dią".

#### Known issues
- Local validation: 374 tests passed and two failed (tray status and the daily
  suggestion limit across UTC/local dates).

### Private build 0.0.3 — 2026-10-26

#### Added
- Updates from the tray: the desktop app checks GitHub releases every few hours
  and offers "Update X available — install". The wheel is verified against the
  release's SHA256SUMS, installed into Dia's own environment, and Dia restarts.
  `[app] check_updates = false` turns the check off; a source checkout is never
  updated this way.

#### Fixed
- The tray context menu opens on KDE again (right click on the icon).
- Clicking the tray icon toggles the window again: a second click hides it;
  opening from the menu or another launcher still brings it to the foreground.
- Tray service status is one line, `Dia 🟢 | Ollama 🔴`: the native tray menu
  cannot show colored text, so the colour is an emoji dot.
- Agents run with English system error messages (`LC_MESSAGES=C`); the guard
  recognises refused reads of secrets by them and missed them on other locales.
- A release tag without Android signing secrets attaches the debug APK
  (`dia-<version>-android-debug.apk`) instead of failing the mobile build.
- Experiment variants are benchmarked one at a time (parallel `git worktree add`
  calls could collide, making a variant lose its metrics).
- Android release builds require all signing secrets and verify the APK
  signature before publishing. Previously CI could upload an unsigned APK
  that Android rejected as an invalid package.

### Private build 0.0.2 — 2026-10-25

Dia measures, remembers why, guards quality and keeps the bigger picture:
agents in a sandbox, experiments and benchmarks, a memory of decisions,
quality guards, goals over weeks. And it installs and starts like an app:
`install.sh` / `install.ps1` with a setup wizard, one icon to start
everything, its own window with a tray icon and title bar, a new KDE
widget, every feature and setting in the app, chat sessions, plain chat
with Claude or ChatGPT.

#### App and desktop
- Dia's own window (Qt WebEngine, `dia[qt]`): Dia's icon on the taskbar, an
  icon in the tray (show/hide, go to a tab, talk, quiet mode, quit);
  minimizing and the window's X hide it to the tray (`[app]
  minimize_to_tray`, `close_to_tray`, `tray`; Settings → Look); one window,
  `dia app --view chat`, `--task ID`.
- Dia's own title bar in its window (like Obsidian or Cursor): no system
  frame, drag by the top bar, double click to maximize, resize at the
  edges, minimize / maximize / close in Dia's colours (`[app]
  custom_titlebar`).
- The KDE widget shows Dia's icon: grey, purple while listening, pulsing
  while speaking, with a badge for what waits for your decision; its popup
  writes to Dia, lists what waits for you, opens tasks and tabs in the app,
  toggles quiet mode and has the emergency stop and resume.
- Everything from the app: skills with arguments, Dia's tools with their
  output (doctor, sandbox, limits, issues, red team, bench, lab...), per
  project launch / test now / measure now / lab, the AI council and "does it
  work?" in the task composer, a brain test, projects and agents editors,
  memory, CI, missions, council, debt, verification, remote access and
  Discord settings, shortcuts, service and widget install.
- A paired phone can get full access (settings and tools; never secrets or
  pairing).
- `dia skill [name] [key=value ...]` (the docs promised it).

#### Fixed
- Minimize-to-tray now hides the desktop window directly from its title bar;
  system minimize events hide it after Qt finishes changing state. Restoring
  from the tray preserves maximization.
- The taskbar showed the Dia diagram editor's icon from themes like Papirus
  ("dia" is its name): Dia's icon is now `io.github.solar9.dia`. Run
  `dia shortcut install` (or Settings → Look → Refresh shortcuts) once.
- The widget's badge counted finished read-only tasks (answers without
  changes): it counts only changes to merge and plans to approve.
- Clashing translations: the composer's placeholder, "Address comments" and
  the verification label showed another screen's text.

#### Install and start
- `scripts/install.sh` (Linux, macOS) and `scripts/install.ps1` (Windows):
  no root, a private virtualenv, the latest release (or a checkout), then
  `dia setup`. Arch: `packaging/arch/PKGBUILD`.
- `dia setup`: finds your coding CLIs, git repositories, Obsidian vault and
  Ollama; writes `~/.config/dia/config.toml`; adds the menu and desktop
  icons, optionally start at login, the systemd service, the KDE widget;
  checks the result.
- One click: `dia shortcut install` (menu, desktop, autostart; Linux,
  Windows, macOS); every shortcut runs `dia app`, which starts everything
  Dia needs if it is not running (the service when installed) and opens
  its window. `dia up` does the same from a terminal.
- Releases are built by CI from a tag: wheel, sdist, installers, checksums.
- The Android and iOS app (`mobile/`): Dia's interface in a native shell
  that pairs with your Dia by QR code; built by CI for Android.

#### Containment
- Agents run in a bubblewrap sandbox: an almost empty home, only their
  worktree, login and tools; the repository's git data read-only except their
  task branch; Dia's secrets out of their environment. Project tests run in it
  too. `dia sandbox check`.
- The guard: decoy secrets in the sandbox; an agent that reads one is stopped
  and the task shows a security incident (UI, audit log, urgent alert).
- `dia redteam`: real agents against a repository full of injected
  instructions; the same attack runs in the test suite with a scripted agent.
- `dia lab`: commands in a throwaway container on a copy of a project.

#### Experiments and measurement
- Benchmarks per project (`benchmark = "..."`): metrics as JSON or
  `name: value` lines, the median of several runs, kept over time; after
  every merge the base branch is measured and a regression is reported with
  the commits that came in. `dia bench`, `/api/projects/{name}/benchmarks`.
- Experiments: one change tried several ways (one variant per agent or per
  approach), each tested and benchmarked against the base branch; a table
  and a recommendation, nothing merged. `dia experiment`, `/api/experiments`,
  "Dia, sprawdź, czy ECS przyspieszy nova", a form in Status.
- Scorecard: Dia's own numbers week by week (tasks done, discards,
  rollbacks, retry rescues, review rounds, minutes per task, incidents,
  benchmark regressions). `dia scorecard`, `/api/scorecard`, Usage view.
- Agents judged by quality: rollbacks, benchmark regressions and extra
  review rounds count against them; proposals and automatic routing use it.
- Shadow brain: requests are logged (`[assistant] log_intents`), and
  `dia brains --replay N --brain X` shows how often another brain would have
  decided the same, without executing anything.

#### A memory of decisions
- Decision log: merges, discards, rollbacks, rejected plans and review
  verdicts, with reasons (`dia merge/discard/rollback ID --reason`, asked in
  the UI). `dia why "..."`, `dia decisions`, `/api/why`, `/api/decisions`,
  the Memory view, and "Dia, dlaczego zrezygnowaliśmy z X?".
- Working-style profile drafted from the decision log and your fixes after
  agents; approved by you, editable, given to agents with every task
  (`dia profile --update/--accept`, `/api/profile`, the Memory view).
- Contradiction check: notes and docs against the code, corrections as
  proposals (`dia contradictions`, a button per project, "sprawdź, czy
  notatki są aktualne").
- Impact analysis: Godot dependency graph, files changed together in git,
  covering tests (`dia impact`, `/api/projects/{name}/impact`, per project in
  Status, "co się może zepsuć, jeśli zmienię dash?").
- A plan can be discarded (rejecting it is a decision too).

#### Quality guards
- Architecture guardian: `ARCHITECTURE.md` rules checked by the reviewer
  (`VIOLATION:` lines) and `architecture_forbid` dependencies checked on
  every change; violations block merging until `--override "why"` (the UI
  asks), recorded as a decision.
- Verification gate: after a large change the author lists its assumptions
  with a check command each; Dia runs them in the sandbox, and a failed one
  blocks merging like a violation (`[verification]`).
- Technical debt register: `dia debt` (`--deps`, `--fix N`),
  `/api/projects/{name}/debt`, a button per project.
- Debugging swarm: `dia debug` (`--fix ID`), `/api/debug`, "znajdź, czemu
  ...", a form in Status; hypotheses from agents in roles, settled by tests.

#### Goals and context
- Goals over weeks: `dia goal new/list/review/approve/close`, `/api/goals`,
  the Missions view, "cel: ..."; milestones, weekly reviews, the next
  mission for your approval.
- Plan simulation on every plan and mission: likely files, expected cost
  from history, risks, approval points (CLI, assistant, task view).
- Work profiles: `dia work start/stop/list`, `[profiles.*]`, `/api/work`,
  "zaczynam pracę nad ...", "kończę na dziś".
- One conversation across devices for the owner (`[assistant]
  one_conversation`, `owner_ids`), kept across restarts.
- Discreet suggestions from Dia's history: `dia suggestions`,
  `/api/suggestions`, `[suggestions]`, through quiet hours and the budget.
- Chat sessions in the app: several conversations, each with its own
  history (kept by Dia, on every device), context and pending plan; rename
  and delete; the main conversation stays shared with voice and Discord.
- Plain chat: a conversation can talk straight to Claude or ChatGPT
  (your subscriptions through Claude Code / Codex, or the APIs with a key,
  or Ollama), with the model chosen in the chat (`[chat]`, `dia[chat]`).
- Crypto prices skill (CoinGecko), also in the briefing.
- Dia's icon everywhere: the app, the installed PWA (maskable), push
  notifications, the KDE widget, and drawn in the terminal by `dia version`;
  the version in the app and in `dia version`.
- Self-check: supervised channels and watchers in `dia serve`,
  `/api/health`, interrupted tasks recorded, `dia doctor --fix`.

### Private build 0.0.1 — 2026-10-25

The first release: a personal assistant that runs coding agents on your
projects, looks after your computer and day, and asks before anything
irreversible. Tested live on Linux (Python 3.14, Godot 4.7, Claude Code,
Codex, Cursor).

#### Agents and work
- Claude Code, Codex, Cursor Agent and any CLI as agent plugins; every task
  in its own git worktree and branch; tests after every change; merging,
  publishing and discarding only on your approval.
- Cross-agent review, multi-step plans and pipelines, missions (a graph of
  steps run in parallel with a budget), AI Council, GitHub/GitLab pull
  requests with CI feedback and review comments, issues to tasks.
- Usage-limit fallback and waiting, retry policies, limits per task (agent
  minutes and calls, call timeout, CPU priority), agent routing by rules or
  record, agent benchmark with proposals, rollback of a merged task.
- Test scenarios ("czy parry działa?"), emergency stop, audit log.

#### Assistant
- A brain chain (rules, local Ollama, subscription models), persona and
  personality, Polish and English, conversation context, replies fit for
  desktop, phone, voice and Discord.
- Skills: weather, news, markets, briefing, computer, services, updates,
  screen and camera (opt-in), security, calendar, mail, Home Assistant,
  Notion, clipboard, tidying Downloads, Godot analysis, game balance.
- Scheduler, Web Push, quiet hours and a notification budget, research
  reports with sources.

#### Memory
- Markdown/Obsidian memory with semantic search, learned project facts,
  personal preferences and how-tos, all kept on your approval.

#### Voice
- Whisper and Piper (or ElevenLabs), push-to-talk and "Hej Dia" without
  training, speaking sentence by sentence with interruptions, speaker
  recognition.

#### Games (Godot)
- Headless tests with GUT/gdUnit4 reports, builds of every export preset
  with changelogs, itch.io and Steam publishing on approval, scene and
  performance analysis, balance from playtest telemetry.

#### Interfaces and security
- A web UI and desktop app, a phone PWA with paired devices, Discord, a KDE
  widget, a CLI.
- Security checks of your own computer, hosts and networks (listening ports,
  scans and device discovery only of what you list, logs, vulnerable
  dependencies). Secrets only in `~/.config/dia/env`.
