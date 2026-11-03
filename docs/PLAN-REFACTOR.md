# Plan — full refactor (behaviour-preserving)

Baseline: `main` @ `46f9f4c` (0.1.2), checked 02.11.2026. 418 tests, ruff clean.
Goal: smaller modules with one job each, the same behaviour, the same public
surface (CLI, HTTP API, `dia.*` entry points, config keys). No features in
these PRs; anything found broken goes to a separate `fix:` commit.

Sizes: **S** ≈ ½ day, **M** ≈ 1½ day, **L** ≈ 3+ days.

---

## Ground rules (every phase)

1. One phase = one branch `refactor/<phase>` = one PR into `main`. Small commits
   (`refactor: …`), each green on its own.
2. Every commit: `pytest -q`, `ruff check .`, `ruff format --check .`.
3. Do not change: `[project.scripts] dia = "dia.cli:main"`, any
   `[project.entry-points."dia.*"]` target (third-party plugins and user configs
   depend on them), HTTP routes and JSON shapes, CLI subcommands/flags, TOML keys.
4. Keep lazy (in-function) imports in CLI/API handlers: they keep `dia --help`
   fast and optional extras optional (CI installs only `.[dev]`).
5. Move code first, change it later: a move commit contains no edits beyond
   imports, so `git log --follow` / review stays readable.
6. After each phase: update `docs/ARCHITECTURE.md` (module map) and a
   `CHANGELOG.md` "Internal" line.

---

## Hotspots found

| File | Lines | Problem |
|---|---|---|
| `src/dia/ui/static/app.js` | 4109 | Whole SPA in one file (~100 components, strings, API client, diff parser). |
| `src/dia/cli.py` | 2300 | 80+ `cmd_*` handlers + a 420-line `build_parser()`; 72 lazy imports. |
| `src/dia/channels/api.py` | 1896 | ~110 routes in one class; `task_action` is a long `if action ==` chain; 72 lazy imports. |
| `src/dia/orchestrator.py` | 1663 | God object: tasks, plans, review, learning, publishing/CI, agent calls/limits, toggles. |
| `src/dia/ui/plasmoid/contents/ui/main.qml` | 896 | One QML file. |
| `src/dia/channels/discord_bot.py` | 821 | Embeds, views, commands and bot in one module. |
| `src/dia/*.py` | 74 flat modules | No grouping; `benchmark.py` vs `benchmarks.py`; ~20 modules hand-roll JSON-file persistence, only 3 write atomically. |
| `src/dia/store.py` | 348 | Schema via `CREATE TABLE IF NOT EXISTS`, no migrations (no way to add a column safely). |
| `docs/test-raports/` + `docs/test-reports/` | — | Two folders, one a typo. |

---

## Phase 0 — safety net (S) · `refactor/safety-net`

Pin the public surface so later moves cannot silently change it.

- [x] `tests/test_surface.py`:
  - CLI snapshot: walk `dia.cli.build_parser()` subparsers → sorted list of
    `(command, option strings)`; compare with `tests/snapshots/cli.json`.
  - API snapshot: `ApiChannel(...).app().router.routes()` → sorted
    `(method, path)`; compare with `tests/snapshots/routes.json`.
  - Entry points: every target in `pyproject.toml` `dia.*` groups imports and
    resolves (`importlib.metadata.entry_points`).
- [x] Add `pytest-cov` to `dev`; record baseline coverage per module in the PR
  description (no gate yet).
- [x] Optional: `import-linter` (dev only) with a first contract:
  `dia.channels` and `dia.cli` may import `dia.orchestrator`, never the reverse.

**Done when:** snapshots committed, CI green.

---

## Phase 1 — CLI package (M) · `refactor/cli`

`src/dia/cli.py` → `src/dia/cli/`:

```
cli/__init__.py      main(), build_parser() (assembles), version_lines()
cli/_common.py       print_report, print_facts, _call_serve, skill_args, helpers
cli/tasks.py         run, tasks, show, diff, merge, discard, rollback, review, plan, publish, ci, comments, launch, stop, quiet
cli/memory.py        remember, memory index/search, learned, howto, why, decisions, profile, preferences, contradictions
cli/quality.py       check, fix-build, security, scorecard, bench, experiment, lab, redteam, sandbox, impact, debt, debug, audit
cli/agents.py        doctor, agents, limits, usage, brains, council, research, scenario
cli/work.py          goal, mission, work, schedule, issues, suggestions, skill
cli/release.py       build, publish-build, changelog
cli/desktop.py       screen, balance, analyze, tidy, runtime, service, secret, shortcut, plasmoid
cli/serve.py         serve, ui, app, mobile (+ _keep_index_fresh, _ui_url, _ui_running)
cli/voice.py         say, voice, speakers
cli/setup.py         setup, version
```

- [ ] Each module exposes `register(sub: argparse._SubParsersAction) -> None`
  that adds its subparsers and `set_defaults(handler=cmd_x)`; `build_parser()`
  calls them in the current order (help output order unchanged).
- [ ] `dia.cli:main` keeps working (`cli/__init__.py`), `python -m dia` too.
- [ ] Update test imports (`from dia.cli import …`) — re-export what tests use
  from `dia.cli` rather than rewriting many tests.

**Done when:** CLI snapshot unchanged, `dia --help` output byte-identical
(diff it before/after), tests green.

---

## Phase 2 — HTTP API package (M) · `refactor/api`

`src/dia/channels/api.py` → `src/dia/channels/api/`:

```
api/__init__.py      ApiChannel (run, guard, websocket, broadcast, app() assembling routes) — entry point unchanged
api/_util.py         api_token, task_json, device_json, pairing, qr_svg, body/JSON helpers, error mapping
api/tasks.py         tasks, task, diff, tests, task_action (dispatch dict), plans, builds
api/cli_sessions.py  /api/cli-sessions*, /api/cli-captured*, /api/cli-commands
api/chat.py          chat, talk, chat providers, sessions, voice
api/settings.py      config, settings, secrets, themes, theme, devices, push
api/projects.py      changelog, analysis, balance, benchmarks, contradictions, impact, debt
api/memory.py        memory*, why, decisions, profile, preferences
api/work.py          goals, missions, work, schedules, suggestions, skills, tools
api/system.py        status, about, health, system, security, usage, scorecard, audit, quiet/screen/camera, desktop, tidy, notifications, stop, resume
```

- [x] Each module: `def routes(ch: ApiChannel) -> list[web.RouteDef]` (or a
  handler class receiving `ch`); `app()` concatenates them in today's order.
- [x] `task_action`: replace the `if action == …` chain with
  `ACTIONS: dict[str, Callable]`; unknown action → same 4xx as today.
- [x] One body parser `await _body(request) -> dict` instead of repeated
  `request.json() if request.can_read_body else {}` + `isinstance(body, dict)`.
- [ ] `pyproject` entry point (if any refers to `dia.channels.api:ApiChannel`)
  and `cli/serve.py` imports keep the same name.

**Done when:** route snapshot unchanged, `tests/test_api.py` green without
behavioural edits.

---

## Phase 3 — split the Orchestrator (L) · `refactor/orchestrator`

Keep `Orchestrator` as the single façade every channel calls (ARCHITECTURE
principle), but move the work into collaborators it owns:

```
core/agent_calls.py   AgentCaller: call_agent, fallbacks, limit handling, _incidents, sandbox_for, limit_status
core/review.py        Reviewer: reviewer_for, review_task, _review, _reviewable
core/forge_flow.py    Publisher: publish_task, _forge, _published, ci_status, fix_ci, review_comments, address_comments, _push_fix, publish_body, comments_prompt, ci_fix_prompt
core/learning.py      Learning: learn, pending_facts, decide_facts, remember, propose_howto, accept_howto, spawn/drain
core/runstate.py      RunState: _read_state/_write_state, quiet/screen/camera toggles, stop_all/resume
orchestrator.py       Orchestrator: run_task, create_plan/run_plan, _execute/_run/_attempt/_fix_tests/_test, merge/rollback/discard, decide, emit, audit + thin delegating methods
```

- [x] Collaborators take explicit dependencies (`store`, `config`, `emit`,
  `audit`, `call_agent`), not the whole Orchestrator, where practical.
- [x] Orchestrator keeps every current public method name as a one-line
  delegate, so `api`, `cli`, `discord_bot`, `voice`, `assistant`, `missions`
  and tests need no changes in this phase.
- [x] Do it in 5 commits (one collaborator each), tests green after each.
- [x] Target: `orchestrator.py` ≤ 700 lines.

**Done when:** tests green unchanged; `tests/test_orchestrator.py` and
`test_review*.py` still drive through `Orchestrator`.

---

## Phase 4 — persistence (M) · `refactor/persistence`

- [x] `src/dia/jsonfile.py`: `read_json(path, default)`, `write_json(path, data)`
  (tmp file + `os.replace`, mode preserved, parent created). Move
  `runtime.py`'s atomic writer here.
- [x] Switch the hand-rolled readers/writers to it: `attention, conversations,
  config (settings.json), devices, issues, limits, preferences, push, secrets,
  schedule, security, suggestions, sessions, tidy, watch, work, debt, impact,
  orchestrator (state)` — one commit per few modules. Keep file names/format.
  `secrets.py`: keep its file permissions (0600) — add a test.
- [x] `store.py`: versioned migrations with `PRAGMA user_version`;
  migration 1 = today's schema (existing DBs detected and stamped as 1, no
  rewrite). Test: open a DB created by the old code → stamped, data intact.

**Done when:** every JSON state file is written atomically (grep finds no
`write_text(json.dumps` outside `jsonfile.py`), migration test green.

---

## Phase 5 — package layout (L) · `refactor/layout`

Group the 74 flat modules. Proposed:

```
dia/core/        orchestrator, store, config, workspace, plans, review, retry, limits, task_limits, sandbox, guard, runtime, plugins, routing, jsonfile, (phase-3 modules)
dia/quality/     quality, debt, impact, contradictions, scorecard, benchmark+benchmarks (merge → benchmarks), experiments, lab, redteam, simulation, scenario, shadow, ci
dia/knowledge/   decisions, learn, profile, preferences, conversations, research, council, suggestions, attention
dia/work/        goals, missions, schedule, swarm, work, issues, watch
dia/desktop/     appwindow, desktop, screen, camera, clipboard, tidy, system, service, processes, devices, push, computer, health
dia/release/     release, update, godot_analysis, balance
dia/ (top)       __init__, __main__, about, banner, assistant, plainchat, persona, security, secrets, setup, audit, sessions
```

- [x] Plugin packages (`agents, brains, channels, forges, memory, skills,
  toolchains, voice, ui`) stay where they are — they are the extension API.
- [x] Only move modules no entry point points at; if one must move, leave a
  re-export at the old path.
- [x] One commit per new package (`git mv` + import rewrite, e.g. with
  `ruff check --fix` for sorting); update `tests/` imports in the same commit.
- [x] Decide first, with the owner, whether old internal import paths need
  shims (internal only → no shims).

**Done when:** `ls src/dia/*.py` ≤ ~15 files, tests green, import-linter
contracts: `core` imports nothing from `channels`, `cli`, `desktop`, `ui`.

---

## Phase 6 — web UI modules (L) · `refactor/ui`

No build step (import map + vendored Preact/htm) — keep it, split into native
ES modules under `src/dia/ui/static/js/`:

```
js/api.js          readToken, api(), websocket
js/i18n.js         STRINGS (en, pl), t()
js/util.js         parseWhen, stamp, dayKey, dayLabel, ago, store, languageOf, urlKey
js/ui/             Code, RichText, Diff (+parseUnifiedDiff), Composer, VSplitter, Meter, Bars, Columns, Palette, Login, WindowControls, DiaLogo
js/views/          tasks.js (TasksView, TaskDetail), inbox.js, chat.js (ChatView, TalkSheet, recordSpeech), cli.js, status.js (+cards), settings.js (+forms), missions.js, memory.js, usage.js
app.js             App + router only
```

- [x] `index.html`: unchanged entry `<script type="module" src="/static/app.js">`.
- [x] `sw.js`: add the new files to the precache list (offline must keep working);
  bump the cache name.
- [x] `tests/test_ui_package.py`: read `STRINGS` from `js/i18n.js`; add a test
  that every `import "./…"` in `static/js/**` resolves to a file and every
  static file is in the sw.js precache list.
- [x] Check the wheel includes `static/js/**` (hatch includes package data;
  verify with `python -m build` + unzip -l).
- [ ] Optional second step: split `style.css` per view the same way.
- [ ] Manual smoke in the Qt window and the browser: every view renders, PL/EN,
  themes, offline reload (note in `docs/test-reports/`).

**Done when:** `app.js` ≤ 300 lines, no file in `js/` > 600 lines, UI smoke
report committed.

---

## Phase 7 — channels and widget (M) · `refactor/channels`

- [x] `channels/discord_bot.py` → `channels/discord/` (`embeds.py`, `views.py`,
  `commands.py`, `bot.py`, `__init__.py` exporting `DiscordChannel`); keep the
  entry point `dia.channels.discord_bot:DiscordChannel` via a re-export module
  (or update pyproject — that changes a user-visible target only for people
  who pinned it; prefer the re-export).
- [x] `channels/voice.py` (533): separate the conversation loop from audio I/O.
- [x] `plasmoid/main.qml` (896): extract components (`TaskList.qml`,
  `StatusHeader.qml`, `Controls.qml`) next to it.
- [x] `assistant.py` (559, 19 lazy imports): intent → handler dispatch table.

---

## Phase 8 — typing (M, can run in parallel after phase 3) · `refactor/typing`

- [x] Add `mypy` to `dev` and CI (job `typecheck`), config in `pyproject.toml`:
  lenient globally, `strict = true` for `dia.core.*` and `dia.store`.
- [x] Replace `Any` at the API boundary with `TypedDict`s for task/device JSON.
- [x] Fix what strict mode finds in core; anything that is a real bug → separate `fix:` commit.

---

## Phase 9 — repo hygiene (S) · `refactor/docs`

- [x] Merge `docs/test-raports/` into `docs/test-reports/` (`git mv`), fix links
  (`grep -rn test-raports`).
- [x] `docs/ARCHITECTURE.md`: new module map and layer rules (the
  import-linter contracts in prose).
- [x] `CONTRIBUTING.md`: where new code goes (which package), "one job per module".
- [x] `CHANGELOG.md`: "Internal: refactor" section for the next release.

---

## Order and estimate

0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 9, with 8 any time after 3.
Phases 1, 2, 6 are independent of each other and can go in parallel branches
after 0. Total ≈ 12–15 days of focused work.

## Progress

| Phase | Status | PR | Notes |
|---|---|---|---|
| 0 safety net | ✅ | | Snapshots: 77 CLI entries, 168 routes. Baseline coverage 76% (15208 stmts). import-linter skipped (optional; add with phase 5). |
| 1 CLI | ✅ | | `--help` of all 77 commands byte-identical. Deviation: instead of `register(sub)` each module exposes `COMMANDS` (name → add function) and `cli/__init__.py` has `ORDER`, because the original registration order interleaves groups and help order had to stay. Kept `set_defaults(fn=...)`. |
| 2 API | ✅ | | Handlers moved as mixin classes (`TaskRoutes`, …) that `ApiChannel` inherits, each module has `routes(ch)`; so `self.` code did not change. Added a test that no route is shadowed (registration order changed). `read_body` keeps exact old semantics (no dict coercion: a non-dict body still fails as before). `STATIC` path fixed for the deeper package. |
| 3 orchestrator | ✅ | | `orchestrator.py` 1663 → 689 lines. Collaborators hold `self.dia` and read config/store through it (so `apply_config` and monkeypatching stay live), not injected copies. Beyond the plan: also `merging`, `inbound` (issues, commit checks, fix-build), `testing`, `planning` to reach the ≤700 target; `spawn/drain` stayed on the Orchestrator (generic); `Event/TaskActionError/TaskReport/new_task_id` moved to `core/types.py`, prompt helpers to `core/prompts.py`, all re-exported from `dia.orchestrator`. `Orchestrator._test` kept as a delegate (missions, release call it). |
| 4 persistence | ✅ | | 20 modules switched to `jsonfile` (all but `config.read_settings`, `tidy` reads and `runtime` reads, whose error handling differs and was kept). `secrets.py` is an env file, not JSON: already 0600 and covered by `test_secrets_tts.py`; `impact` has no state file. Files now also get created with parents. `push.json` is now always 0600. A DB from a newer Dia only logs a warning. |
| 5 layout | ✅ | | No shims (owner delegated the choice; internal modules, pre-1.0). Deviations: old `review.py` → `core/review_prompts.py` (name clash with the phase-3 `core/review.py`); `benchmark.py` → `quality/agent_stats.py` instead of merging two unrelated modules; `processes` and `devices` live in `core` (not `desktop`) and `runtime` in `desktop`, plus new `core/paths.py`, so that `core` imports no interface; string monkeypatch target in `test_setup.py` and two embedded scripts in `test_appwindow.py` updated; `ICONS` paths fixed. 12 top-level files left. `lint-imports` added to dev extras and CI. |
| 6 web UI | ✅ | | `app.js` 4109 → 288 lines + 25 modules (max 556). Split done by script (acorn + ESLint `no-undef` to derive imports); `token/lang/onPhone` got setters. Verified by ESLint, import checks, new tests and a QtWebEngine smoke of all views (EN, and PL for five); see `docs/test-reports/2026-11-02-ui-modules.md`. **Manual pass of themes, phone layout, palette, voice, offline reload and the real window is still open.** Beyond the plan: `ui/logo`, `ui/icons`, `ui/charts`, `ui/window`, `views/settings_forms` / `settings_devices`; `decisionOf`/`RUNNING` live in `views/tasks` to avoid an import cycle. |
| 7 channels | ✅ | | `discord_bot.py` (821) → `channels/discord/` (+ a re-export `discord_bot.py` for the entry point); `channels/voice.py` (533) → `channels/voice/` (`__init__` core + `AudioMixin`, `ConversationMixin`, `helpers`; same module path, so the entry point and `talk.py` imports work); `assistant.py` `_execute` if-chain → `ACTIONS` table + `_do_*` handlers; `main.qml` 896 → 506 + 5 components, loaded in QtQml with a mock panel by `tests/test_plasmoid_qml.py` (needs PySide6, run in the CI `qt` job). **The widget was not run in a real Plasma shell**: check it once (`dia plasmoid install`). The popup footer (views, quick switches) stayed in main.qml. |
| 8 typing | ✅ | | `mypy` in dev extras + CI job `typecheck`. Strict = the flags spelled out for `dia.core.*` (mypy ignores `strict` in a per-module section); core is clean. The route/voice mixins got typed base classes (`ApiBase`, `VoiceBase`) declaring what they expect from the channel. `TaskJson`/`DeviceJson` TypedDicts (pinned to the dataclasses by a test). **31 modules are parked with `ignore_errors` (106 findings, listed in `pyproject.toml`)**: mostly Optional intent/store values passed on unchecked, which needs a decision rather than a mechanical fix. No confirmed bugs found (schedule's `Cron(*…)` is a false positive); one behaviour change: `forge_flow` raises `TaskActionError` for a task without a branch. |
| 9 docs | ✅ | | `test-raports` merged into `test-reports` (README index updated, the release script no longer lists the old name; the historical reports keep their text). ARCHITECTURE has the module map and layer rules (written phase by phase), CONTRIBUTING has "Where new code goes". |
