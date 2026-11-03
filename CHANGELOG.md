# Changelog

All notable changes to Dia. Versions follow [Semantic Versioning](https://semver.org/);
before 1.0 a minor version may change the configuration.

## [Unreleased]

## [0.1.3] — 2026-11-04

A stabilisation release: the refactor of 0.1.2's code base is shipped, the UI audit is closed,
the web UI, the window and the tray got a long list of small fixes, and Dia speaks five more
languages. **If you only use Dia, nothing needs to be done; if you write plugins or import `dia`
modules, read "Internal".**

### Added
- The web UI is translated into German, French, Spanish, Italian and Portuguese (choose the
  language in Settings → Dia), in full: every string Polish and English have. The translations were
  written by the assistant and have **not been reviewed by native speakers**. The service words
  and the tray menu follow the language; the Plasma widget's own labels and Dia's server messages
  (answers of `dia say`, voice phrases) are still Polish/English only (`static/js/lang/` is where a
  language is added).
- A **System** theme (Settings → Look) for the app and the phone: light or dark as the system says,
  following it when it changes. The browser's and the PWA's bars take the theme's background.
- Before an agent starts, Dia says what she understood (`code change · nova · claude`) in chat,
  Discord, by voice and in `dia say`; a plan's "run it?" starts with it.
- The Status page opens with a summary row: service, sandbox, agents, running, waiting for you.
- A "Check for updates" item in the tray that shows the result of the last check.
- Dia's window remembers its size, position and whether it was maximised, and comes back on a screen
  that exists (an unplugged monitor or a smaller resolution no longer leaves it off-screen).

### Changed
- **One count everywhere.** "Running" and "waiting for you" are counted once, by the API (`counts`
  in `/api/status`, `decision` on each task), so the web UI, the tray and the Plasma widget agree;
  the widget now also counts failed CI and review comments. Running tasks show how long they run.
- **One set of service words.** Dia and Ollama show the same state words (Running, Stopped, Error,
  Starting…, Not installed) in the tray, the widget and Settings. Start/Stop/Restart are enabled only
  when they make sense for the state, stop/restart ask first, and the result is shown (Settings, a toast,
  a tray notification, the widget). `dia runtime status` and `/api/desktop` gained `state`, `label`,
  `actions`, `words` and an operation `label`.
- **The web UI says what is going on.** Everything it fetches shows "Loading…", an error with a Retry
  button, or an empty message instead of staying blank when a request fails.
- **One translation system** in the web UI: task statuses, units and the services card are translated,
  relative times follow the language, and a test fails when a key is missing in Polish or English.
- **Own dialogs** (themed, translated, keyboard friendly) replace the browser's confirm/prompt boxes.
- **Login** is a proper form: a password field, Enter submits, an empty token shows an error.
- **Chat:** a "Dia is thinking…" bubble while she answers, a multi-line input (Shift+Enter for a new
  line) and plan buttons that say what they do ("Yes, run the plan").
- **Accessibility:** icon-only buttons are labelled, toasts are announced by screen readers, and the
  conversation and session lists work with the keyboard.
- **Tray:** clearer wording for closing the window (Dia keeps running) versus stopping Dia; every text
  in the seven interface languages.
- **"Dia is not running" page** uses the current theme and its own title bar, and says whether Dia is
  starting, stopped, failed to start (with a button for the logs) or not set up.
- **Plasma widget:** it polls much less while the popup is closed (a slow look every 30 s keeps the
  badge true), says what to do when Dia refuses its token, scrolls long answers instead of cutting
  them off, and never sends an empty prompt.

### Fixed
- CLI sessions: taken-over and running sessions are listed together, newest first.
- A timed-out agent or test command no longer leaves helper processes running: the whole process
  group is ended (on Python 3.11 they also held the call up until they quit).
- Agents (and project tests) can run `pytest` and the project's other Python tools inside the sandbox:
  the repository's `.venv`/`venv` is available read-only and first on `PATH`, and the worktree's `src`
  goes first on `PYTHONPATH`, so an editable install tests the agent's code. No access to your secrets
  or the rest of your home was added.
- A model's own choice of agent no longer overrides routing and the default: an agent is used only if
  you named it or routing picks it. A clarifying question from the model stays a conversation and no
  longer creates a read-only task.
- When a request needs a project and the model gave none (debug, impact, goal, scenario…), Dia asks
  "Which project is this about?" instead of failing with "unknown project 'None'"; a missing prompt
  falls back to what you said.
- Answering a waiting plan with yes or no works in German, French, Spanish, Italian and Portuguese
  ("ja", "oui", "sí"…); before, only Polish and English words were understood.
- The CI watcher no longer stops on a task that was discarded while its CI was being asked; `dia comments`
  and `dia goal review` on an unknown id say so instead of a traceback; the background memory-index
  refresher no longer fails with a memory backend that has no semantic index.

### Internal
- **Import paths changed, plugin entry points did not.** The flat `dia/*.py` modules moved into
  `dia.core`, `dia.quality`, `dia.knowledge`, `dia.work`, `dia.desktop` and `dia.release` (no shims;
  `dia.limits` is now `dia.core.limits`, and so on). Code that imports Dia's internals must follow;
  plugins registered through entry points (`dia.agents`, `dia.brains`, `dia.channels`, …) are unaffected,
  and the CLI, the HTTP routes and the TOML keys are unchanged (pinned by `tests/test_surface.py`).
- Refactor phases 0–9: `dia.cli` and `dia.channels.api` are packages of small modules; the Orchestrator
  is a façade over collaborators in `dia.core` (689 lines, was 1663); state files go through
  `dia.core.jsonfile`, the SQLite schema is versioned; the web UI's `app.js` is split into native ES
  modules (`static/js`, no build step); the Discord and voice channels are packages and the assistant
  dispatches intents through an action table; the Plasma widget's `main.qml` is split into components;
  `lint-imports` keeps `dia.core` free of interface imports; `mypy` runs in CI (strict for `dia.core`).
  A task without a branch now fails publishing with a clear message instead of passing `None` on.
- mypy: 20 more modules are type-checked (31 had `ignore_errors`, 11 are left; the list is in
  `pyproject.toml`).
- Tests: direct tests for the assistant's action table, the store, release and update logic, the persona
  prompt and the Discord channel (no network); coverage of those modules went from 41–99 % to 96–100 %,
  the whole package from 77 % to 79 %. CI now reports coverage (`coverage.xml`, no gate yet).
- `scripts/ui_smoke.py` runs an offscreen smoke test of every web UI view in any language (also with
  failing requests); the manual checklist for the window and the widget is in
  `docs/test-reports/2026-11-03-ui-smoke-0.1.3.md`.
- `docs/test-raports` was merged into `docs/test-reports`; CONTRIBUTING says where new code goes.

## [0.1.2] — 2026-10-30

### Added
- Date and time on messages in Chat, Talk and CLI sessions.
- Slash commands in taken-over CLI sessions, matching each agent's own CLI.
- About Dia (Status and Settings): author, solar9.me, GitHub, license, and
  versions of Dia, Python, Qt and installed CLIs. `dia version` lists the same.

### Changed
- Status, Usage and Settings reflow with the window. Status stacks in one
  column; Settings is a single readable column.

### Fixed
- Starting `dia-session.target` no longer waits for local-brain warmup.
- Task Changes tab, resizable panes, and Plasma widget mute/stop icons.
- CLI agent replies inherit the user turn's time when the transcript (Cursor)
  only stamps the human side.
- The Qt window picks up CSS/JS after a reload (cache-bust of the app shell).

## [0.1.1] — 2026-10-28

### Added
- UI 2.0: Inbox start view, Settings side-nav groups, Research from the composer,
  themes shared with the phone and Plasma widget, task detail with a decision bar,
  Ctrl+K, and CLI sessions (start, take over, release) in the app.
- Release hygiene: one version source (`scripts/bump-version`), CI on Python 3.11 /
  3.13 / 3.14 plus a Qt job, publish only after green CI, `docs/RELEASING.md`.
- Local brain recommendation: `qwen3.5:4b` (best measured 25.10.2026).

### Fixed
- Tasks started together on one repository (experiments, missions) no longer fail now
  and then because `git worktree add`, `remove` and branch deletion raced on git's own
  files; they now take turns per repository.
- Codex / Cursor auto-context no longer appears as a fake user message in CLI sessions.
- Pacman installs are never updated with `pip`; the tray points at the package manager.
- Pre-reset private builds numbered 0.1.0–0.2.3 see ≥0.1.1 as a newer release.
- Merge / push / discard wording no longer becomes an agent `run` task.
- Loud warning when agents would run without a sandbox.

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
