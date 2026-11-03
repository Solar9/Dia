# Plan 0.1.3 — stabilisation release

Baseline: `main` @ `2de7b4a` (0.1.2 + the full refactor, phases 0–9 of
[PLAN-REFACTOR.md](PLAN-REFACTOR.md)), checked 02.11.2026.
Backlog IDs come from the 0.1.1 analysis (`~/Pobrane/Dia — backlog i plan 0.1.1.pdf`)
and [PLAN-0.1.1.md](PLAN-0.1.1.md).

**What 0.1.3 is:** ship the refactor safely (finish the manual checks it left open),
close the UI audit (DIA-48–63), measure coverage and pay down test and type debt.
Security work (Landlock, red-team fixtures, network guard, signed checksums) is
the theme of **0.2.0**, not this release.

Scope: **every must-have and every nice-to-have below**. Must ≈ 3 days, nice ≈ 5 days.
Sizes: **S** ≈ ½ day, **M** ≈ 1½ day, **L** ≈ 3+ days.

---

## Coverage baseline

Measured 02.11.2026 on `main` @ `2de7b4a`, Python 3.14, without Qt extras
(`pytest --cov=dia`): **77 %** (15714 statements, 3666 missed, 437 tests).
The CI `qt` job's tests (window, QML) are not included.

DIA-36 modules, before → after (03.11.2026, same measurement, 684 tests):

| Module | Before | After |
|---|---|---|
| `assistant` | 76 % | 99 % |
| `core/store` | 99 % | 100 % |
| `release/release` | 88 % | 96 % |
| `release/update` | 87 % | 96 % |
| `persona` | 96 % | 100 % |
| `channels/discord/bot` | 60 % | 99 % |
| `channels/discord/commands` | 41 % | 97 % |
| `channels/discord/embeds` | 75 % | 100 % |
| `channels/discord/views` | 51 % | 99 % |
| **whole package** | **77 %** | **79 %** |

Weakest areas overall: `cli/*` (17–45 %), `channels/api/{projects,system,work,tasks}`
(53–64 %), `security` (64 %), `plainchat` (62 %), `desktop/computer` (41 %).

---

## Release criteria (0.1.3)

1. Every item below meets its "done when", or is consciously deferred with a note
   in CHANGELOG and in this file.
2. `publish.yml` publishes `v0.1.3` only after green CI on the tagged commit:
   tests on 3.11 / 3.13 / 3.14, the `qt` job, `typecheck`, `lint-imports`, ruff.
   Published tags are never moved (a fix after tagging → 0.1.4).
3. `scripts/bump-version --check` passes: every version place says `0.1.3`.
4. CHANGELOG `[0.1.3]` has an "Internal" section for the refactor saying that
   internal import paths changed and plugin entry points did not.
5. Manual reports in `docs/test-reports/`: UI after the module split (M1),
   Plasma widget in a real shell (M2), release channel 0.1.2 → 0.1.3 (M4).

---

## Ground rules

- One topic = one branch (`fix/…`, `feat/…`, `test/…`, `chore/…`) = one PR into `main`.
- Every commit: `pytest -q`, `ruff check .`, `ruff format --check .`; for typed
  modules `mypy`; `lint-imports` when imports move.
- Do not change the public surface without a reason in the PR: CLI subcommands
  and flags (`tests/snapshots/cli.json`), HTTP routes (`tests/snapshots/routes.json`),
  entry points, TOML keys. A deliberate change updates the snapshot in the same commit.
- New code goes where CONTRIBUTING.md "Where new code goes" says; `dia.core`
  imports no interface module.
- UI strings in both languages (`static/js/i18n.js`); new static files go into the
  `sw.js` precache list and bump the cache name.
- Tick the item here and add a CHANGELOG `[Unreleased]` line in the same PR.

---

## Must-have

Order: M5 (coverage, so later work is measured) → M1 + M2 (manual checks; they
feed M3) → M3 → M6 → tag → M4.

| Status | ID | Title | Size | Done when |
|---|---|---|---|---|
| ✅ | **M1** (refactor phase 6) | Manual smoke of the web UI after the ES-module split | S | Checked by hand in the Qt window (`dia app`) and a browser: every theme, phone layout (narrow window / DevTools), Ctrl+K palette, voice/Talk sheet, offline reload through the service worker (cache `dia-shell-v18`+), tray show/hide, PL and EN. Anything broken → `fix:` commit. Report `docs/test-reports/2026-11-XX-ui-smoke-0.1.3.md`. |
| ✅ | **M2** (refactor phase 7) | Plasma widget in a real Plasma 6 shell after the QML split | S | `dia plasmoid install`, widget on the panel: StatusHeader, Controls, TaskList, WaitingCard, TaskRow and the popup footer work; mute/stop icons; no QML warnings in `journalctl --user`. Note in the M1 report. |
| ✅ | **DIA-48** | One service-status dictionary (Dia, Ollama) for tray, widget and web, both languages | S | One source of status names/labels; tray, widget and web show the same words for the same state (PL/EN); test pins the dictionary. |
| ✅ | **DIA-49** | Start/Stop/Restart of services: state-dependent buttons, clear confirmation, visible result | S | Only meaningful buttons are enabled per state; destructive ones confirm; the result (ok / error text) is shown, not silent. |
| ✅ | **DIA-50** | Web UI: distinct loading, error and empty states (no silent errors) | M | Every view that fetches shows loading → data / empty / error; a failed `api()` call is visible to the user. Shared component in `js/ui/`. |
| ✅ | **DIA-51** | Working agents and "waiting for you": the same counters everywhere, duration for running tasks | S | Inbox, Status, tray, widget and phone compute counts from one place (API field); running tasks show elapsed time. |
| ✅ | **DIA-52** | Task status translations and leftover English strings; one i18n system | S | No hard-coded user-visible English in `static/js/**` outside `i18n.js`; a test fails on a missing key in either language. |
| ✅ | **DIA-53** | "Dia is not running" page in the window: theme, title bar, starting/stopped/error state | S | Offline page uses the current theme and the custom title bar and says which of the three states it is in. |
| ✅ | **DIA-37** (M5) | Coverage report in CI | S | CI uploads `coverage.xml` + a terminal summary (`--cov=dia --cov-report=term-missing:skip-covered`); no gate yet; baseline recorded here (see "Coverage baseline" below). |
| ✅ | **M6** | Release hygiene | S | CHANGELOG `[Unreleased]` → `[0.1.3] — <date>`; `scripts/bump-version 0.1.3`; ROADMAP gets a 0.1.3 line and "Next" → 0.2.0; this file's statuses up to date. |
| ⬜ | **DIA-01** (M4) | End-to-end release channel check, 0.1.2 → 0.1.3 | S | After the tag: clean install from Solar9/Dia assets (wheel and PKGBUILD), tray "check for updates" sees 0.1.3 from 0.1.2, pacman install is pointed at pacman (not pip), SHA256SUMS match. Report in `docs/test-reports/`. |

---

## Nice-to-have (all planned for 0.1.3, after the musts)

### Agents and sandbox

| Status | ID | Title | Size | Done when |
|---|---|---|---|---|
| ✅ | **DIA-23** | Agents cannot run pytest inside the sandbox | S–M | Reproduce first (`dia sandbox` / a task on Dia's own repo that runs `pytest`). If real: fix the bubblewrap profile (venv, `/tmp`, cache dirs, `PYTHONPATH`) without widening access to secrets; regression test; red-team suite still green. If not reproducible: note why and close. **If confirmed, treat as must.** |

### Assistant: intent clarity

| Status | ID | Title | Size | Done when |
|---|---|---|---|---|
| ✅ | **DIA-12** | Show the recognised intent (action · project · agent) before starting | S | Chat/Discord/voice reply shows the parsed intent before a task starts (or with the "yes?" for approvals); test on the assistant's action table. |
| ✅ | **DIA-13** | Reject an agent the user did not name (QW-01) | S | If the brain returns an agent not mentioned by the user and not the routing choice, it is replaced by routing/default; test with a scripted brain. |
| ✅ | **DIA-14** | A clarifying question stays chat, not `ask` (QW-02) | S | A brain reply that is a question to the user is answered as chat, no `ask` task created; test. |

### UI audit leftovers

| Status | ID | Title | Size | Done when |
|---|---|---|---|---|
| ✅ | **DIA-54** | Window remembers size, position and maximisation | S | `appwindow` saves/restores geometry (atomic JSON via `dia.jsonfile`); off-screen positions clamped; Qt test. |
| ✅ | **DIA-55** | Themes: fix undefined `--muted`, add a "system" theme, `theme-color` per theme | S | No undefined CSS variables (test greps `var(--x)` vs definitions); "system" follows `prefers-color-scheme`; meta `theme-color` follows the theme. |
| ✅ | **DIA-56** | Accessibility basics: labels on icon buttons, announced toasts, keyboard-reachable rows | S | Every icon-only button has `aria-label`/`title`; toasts in an `aria-live` region; list rows focusable and open on Enter. |
| ✅ | **DIA-57** | Login screen: a real form (Enter submits, password field, empty token rejected) | S | `<form>` with `type="password"`, submit on Enter, empty input shows an error. |
| ✅ | **DIA-58** | Replace native `prompt()`/`confirm()` in the web UI with own dialogs | S | No `prompt(`/`confirm(`/`alert(` left in `static/js/**` (test); one `Dialog` component, works in the Qt window and on the phone. |
| ✅ | **DIA-59** | Plasma widget polish: no polling while collapsed, 401 message, long answers, empty prompt | S | Timer stops when collapsed; 401 shows "pair again / token"; long answers scroll; empty prompt not sent. QML test where possible. |
| ✅ | **DIA-60** | Chat: "Dia is thinking…" bubble, multi-line input, plan buttons that cannot be misread | S | Pending bubble while waiting; Shift+Enter newline; plan approve/reject buttons labelled with the action. |
| ✅ | **DIA-62** | Tray menu: clear "Quit", texts in `LABELS`, "Check for updates" with the last result | S | All tray strings in `LABELS` (PL/EN); quit wording distinguishes "close window" vs "quit Dia"; last check time/result in the menu. |
| ✅ | **DIA-63** | Status page: summary row first (service, sandbox, agents, running, waiting for you) | S | One summary row at the top, using the DIA-51 counters. |

(DIA-61 has no entry in the source backlog; check during M1 whether anything is missing.)

### Tests and types

| Status | ID | Title | Size | Done when |
|---|---|---|---|---|
| ✅ | **DIA-36** | Tests for `assistant`, `store`, `release`, `persona`, `channels.discord` | M | Each gets direct tests of its main paths (assistant action table, store migrations/queries, release/update version logic, persona prompt building, Discord embeds/commands without a network); coverage of each up vs. the M5 baseline (record before/after here). |
| ✅ | **T1** | mypy debt burn-down | M | The `ignore_errors` list in `pyproject.toml` (31 modules, 106 findings) shrinks; first `dia.assistant` and every module that passes Optional intent/store values on. Real bugs → separate `fix:` commits. Target: ≤ 15 modules left; record the count here. |

---

## Deferred to 0.2.0 (containment and security)

DIA-28 Landlock as a second sandbox layer · DIA-30 red-team injection through issues,
web pages and review comments · DIA-31 watching agents' network use · DIA-05 signed
SHA256SUMS verified by the updater · DIA-32 live `sandbox check` / `redteam` with Codex
and Cursor · DIA-16 / DIA-18 local-brain routing benchmark and latency · DIA-17
`reasoning_effort`/`think` for OpenAI-compatible brains · DIA-22 mission failure modes
as integration tests · DIA-24 voice false wake-ups · DIA-20 live review of "On your
machine" items · DIA-21 / DIA-04 physical phone and APK signing.

---

## Progress

| Area | Status | PR | Notes |
|---|---|---|---|
| Coverage baseline (M5) | ✅ | chore/coverage-ci | Total 77 %. |
| Manual UI + widget (M1, M2) | ✅ | | Walked through by the owner on 04.11.2026 (report: docs/test-reports/2026-11-03-ui-smoke-0.1.3.md): all fine; the one finding (CLI sessions list order) was fixed in #53. |
| UI audit DIA-48–53 | ✅ | feat/service-status-dictionary (48), feat/service-actions (49), feat/ui-load-states (50), feat/shared-counters (51), fix/ui-i18n (52), feat/offline-page (53) | all six done. |
| Sandbox DIA-23 | ✅ | fix/sandbox-pytest | Real; fixed. |
| Assistant DIA-12–14 | ✅ | feat/assistant-intents | |
| UI polish DIA-54–60, 62, 63 | ✅ | feat/window-geometry (54), feat/themes-system (55); 56–60, 62, 63 in the release PR | all done |
| Tests DIA-36 | ✅ | release PR | 9 modules at 96–100 % (was 41–99 %) |
| Types T1 | ✅ | release PR | 31 → 11 modules in `ignore_errors` |
| Release M6, tag, DIA-01 | 🔶 | release PR | M6 done (changelog `[0.1.3]`, version 0.1.3 in all 9 places, ROADMAP). **Tag and DIA-01 are the owner's**: M1 and M2 are done; tag only on the owner's explicit yes and green CI on the tagged commit. |

## Work log

- **02.11.2026** — plan written; scope: all must + all nice.
- **02.11.2026** — M5: CI runs pytest with coverage and uploads `coverage.xml`; baseline 77 %. `.coverage` was tracked in git by mistake, now untracked and ignored.
- **02.11.2026** — DIA-48: `runtime.STATE_LABELS` is the one dictionary of service states (PL/EN); `unit_state` returns `state` and `label`, the tray, widget and web settings read them. Tray menu now shows the word next to the dot. SW cache v19.
- **02.11.2026** — DIA-49: `runtime.allowed_verbs` decides which of Start/Stop/Restart make sense per state (exposed as `actions`); web, tray and widget enable only those, use the shared verb words, confirm stop/restart naming the service, and show the result (web: line + toast, tray: notification, widget: line under the services). SW cache v20. The web confirm is still the native `confirm()` until DIA-58.
- **02.11.2026** — DIA-50: `js/ui/resource.js` (`useResource`, `<Resource>`, `<ResourceState>`) gives every fetching view loading → data / empty / error with Retry; `App` shows a banner when tasks or status fail to load. Converted: inbox, tasks list, missions, goals, activity, chat providers, CLI sessions, memory, usage, status cards, settings (desktop, notifications, devices). Views that already toast their errors (settings forms, secrets, schedules, task diff/tests) keep the toast. A test fails on a one-line `api(...).catch(() => …)`. Verified in offscreen QtWebEngine against a live `ApiChannel`: all 9 views render clean in EN, and with injected fetch failures show the error state in PL. SW cache v21.
- **02.11.2026** — DIA-51: `dia.core.taskstate` (`decision_of`, `counts`) is the one rule. `/api/status` has `counts {running, waiting_for_you}`, every task JSON has `decision` (merge | plan | ci | comments | null). Web badges and Inbox, the tray (new line in the menu) and the widget (badge, header, tooltip) read them; the widget used to ignore CI/comments decisions, the web did not. Running tasks show `running 4m` / `trwa 4m` (web lists and inbox, widget TaskRow). The web refreshes the status 400 ms after a task event. SW cache v22.
- **02.11.2026** — DIA-52: one i18n system. The per-file `tr(en, pl)` in settings_devices is gone (10 strings now in `i18n.js`); task/step statuses are translated (`st_*` keys, `tStatus`, used by `Pill` and the status filter); leftover English (`calls`, `min`, `breadcrumb`) and the relative-time units (`unit_s/m/h/d`) are keys; a base vocabulary of ~65 common words (OK, Close, Delete, Back, Copy, Error, …) is in both languages. Tests: every `t("key")` the UI uses (647 calls) exists in both languages; no `tr =` helper or `lang === "pl" ? "…"` ternaries. SW cache v23. More languages are a separate change (not in the plan).
- **02.11.2026** — Extra (requested, not in the plan): basic translations de/fr/es/it/pt in `js/lang/` (151 keys each; the rest falls back to English), language selector lists all seven, locale formats follow the language, persona prompt and service-state words know the new languages. Needs a native-speaker review before release. `i18n.js` is exactly at the 600-line module limit: the next big string batch goes to a new file. SW cache v24.
- **02.11.2026** — Languages completed: de/fr/es/it/pt now have all 834 UI keys (684 more each; placeholders checked by a test, files are one string per line and exempt from the 600-line limit). Tray menu texts and the widget's QML labels are still pl/en: they move to dictionaries with DIA-62 / DIA-59 and get the new languages there. SW cache v25.
- **02.11.2026** — DIA-53: the window's "Dia is not running" page is `dia.desktop.offline` (pure Python): colours from the current theme's CSS variables (read each time the page is built), the custom title bar when frameless, and one of four states — starting, stopped, failed to start (with a Show-logs button), service not set up — taken from the unit state (`offline_state`). The window pushes a state change into the open page (`diaOfflineState`), no reload. Words in all seven languages. Checked in offscreen QtWebEngine: DOM, theme colours and buttons per state/language (light/pl/error, midnight/de/stopped, dark/en/starting, light/fr/missing). The UI audit DIA-48–53 is closed.
- **03.11.2026** — DIA-23 reproduced and fixed. In a worktree of Dia's own repo, inside `for_agent`'s sandbox: `pytest` was not on `PATH` (the project's `.venv` lives in the main checkout, hidden under the empty home; the host's `PATH` entry pointed nowhere), system Python has no pytest, and an editable install points at the main checkout. A venv created inside the worktree worked (the whole suite passed), so the bubblewrap profile itself was fine. Fix: `.venv`/`venv` of the repository is bound read-only (same path), put first on `PATH`, `VIRTUAL_ENV` set, worktree `src` first on `PYTHONPATH` (via `bwrap --setenv`, so agents and test runs both get it); `~/.local/share/uv` and `~/.pyenv` joined the read-only tool dirs. Nothing about secrets widened; guard and red-team tests green. Verified on Dia's own repo: bare `pytest` runs and imports the worktree's `dia`.
- **03.11.2026** — DIA-12/13/14: `Assistant.understood()` / `announce()` give `code change · nova · claude` (INTENT_LABELS pl/en; a test checks every action is either labelled or listed as silent). Shown by web chat, Discord (run/ask header and plan message), voice (spoken variant) and `dia say`; a plan's approval text starts with it (not read out). `guard_agent` drops an agent the user did not name unless it is the routing choice (names, Claude/ChatGPT aliases, inflection, no 1–2 letter prefix matches); `guard_clarifying` turns a run/ask/plan/mission whose reply ends in `?` into chat. Both run for every brain in `Assistant._vet`. Three existing tests that pinned the exact reply text were updated.
- **03.11.2026** — DIA-54: `dia.desktop.geometry` (Qt-free: `load`, `save`, `fit`) keeps the window's size, position and maximised state in `window.json` (atomic, via `dia.core.jsonfile`); written 0.5 s after the last move/resize and on close; at start the saved rectangle is fitted to the screens that exist now (pulled back, shrunk, or moved to the nearest screen if its monitor is gone). Maximised comes back maximised with the normal size kept. Found on the way: restoring the maximised state before the page existed raised in `changeEvent` (frameless) — the state is set after `setCentralWidget`. Qt tests run in a fresh process and report through a file, because an exception inside a Qt callback does not change the exit code. Wayland ignores positions; the size still comes back.
- **03.11.2026** — DIA-55: (1) the undefined `--muted` is already gone from the tree; a test now fails on any `var(--x)` that no theme, `style.css` or script defines (layout sizes set from script are recognised). (2) New theme `system` for the app and the phone: `theme.SYSTEM`, `valid()`, `concrete()`; the page resolves it with `prefers-color-scheme` and follows changes; the KDE widget cannot have it (a clear error), and "same as the app" gives it dark. The window's offline page asks Qt for the scheme. (3) `<meta name="theme-color">` follows the theme's `--bg`. Checked in QtWebEngine: theme-color equals `--bg` for light/midnight/dark, and `system` → light with a light OS; the dark-OS branch could not be driven (offscreen QtWebEngine ignores `setColorScheme`), so it was verified in node with a stubbed `matchMedia` (follow on change, midnight stays put). SW cache v26. New string in all 7 languages.
- **03.11.2026** — DIA-56: icon-only buttons all have an accessible name (the `+` in preferences, rename/delete in chat, the three sense buttons; a test scans every `<button>`); toasts sit in an `aria-live` region (errors `role=alert`); the sessions lists are buttons now (chat: an open button beside rename/delete, CLI: the row is a button), rename/delete show on keyboard focus too, and focus-visible outlines were added. SW cache v27.
- **03.11.2026** — DIA-57: the login screen is a `<form>`: the token is a password field with a label, focused on open; Enter or the button submits; an empty (or blank) token shows an error and sends nothing, typing clears it. Driven in QtWebEngine against a live server (form, type, focus, empty and blank refused, nothing stored, error cleared on typing). A token the server rejects still returns to the login screen without a message (app.js is at its 300-line limit). SW cache v28.
- **03.11.2026** — DIA-58: `js/ui/dialog.js` replaces all 15 native `confirm()` / `prompt()` calls (stop-all, rename/delete conversation, capture a CLI session, remove an entity, service actions, full access, merge/discard reasons and override, publish, rollback, red-team, skill questions). Promise API (`confirmDialog`, `promptDialog`), themed, translated (cancel/OK), dangerous ones use the red button and `alertdialog`; Esc/backdrop cancel, Enter confirms, Tab stays inside, focus returns to the opener, several at once queue up. It mounts itself, so `app.js` stays at 300 lines. Driven in QtWebEngine (roles, focus, Tab wrap, Esc, backdrop, prompt value, queue). The service-action confirm of DIA-49 is now this dialog too. SW cache v29.
- **03.11.2026** — DIA-60: chat shows a "Dia is thinking…" bubble (animated dots, `role=status`, still under reduced motion) while a reply is awaited; the input is a growing textarea (Enter sends, Shift+Enter is a new line, an IME composition is not sent); the plan buttons read "Yes, run the plan" / "No, drop the plan" and send the language-independent `yes`/`no` while the bubble shows the label. Driven in QtWebEngine with a delayed /api/chat. SW cache v30.
- **03.11.2026** — fix found on the way: the assistant's yes/no (`_YES` / `_NO`) knew only Polish and English, so "ja" / "oui" / "sí" / "sì" / "sim" (and the no's) did not answer a waiting plan in the new interface languages. Added.
- **03.11.2026** — DIA-59: widget — (1) **polling**: the popup's own timers stop when it is collapsed: the services' state is polled only while open (or while Dia is down, for the tooltip), at 30 s instead of 4 s; the status look keeps a slow 30 s tick while collapsed (open: 4 s, 0.7 s while the voice is busy) — a deliberate deviation from "the timer stops": a fully stopped timer would freeze the panel icon's waiting-for-you badge and the lit icon; opening the popup refreshes at once. (2) **401/403**: the widget still asks `dia ui` for a fresh token once; a second refusal in a row says "Dia refused the widget's token. Run `dia ui` once, or pair the widget again" (PL too). (3) **long answers** scroll in a box of at most 160 px instead of being cut at 8 lines. (4) **empty prompt**: `send()` returns false for an empty or blank prompt and the field is only cleared when something was sent. QML tests: a long answer is boxed and scrolls, a short one is not; the timer, 401 and send rules are pinned. Not run in a real Plasma shell (M2).
- **03.11.2026** — DIA-62: every text of the window and tray is in `dia.desktop.labels.LABELS` (about 50 keys, all seven languages; `appwindow` had a dozen `"x" if pl else "y"` ternaries, now none — a test fails if one returns). The two ways out are worded apart: "Close window and icon (Dia keeps running)" and "Stop Dia and quit". New permanent menu item **Check for updates** that checks at once and keeps the last result in its text ("— up to date, checked 14:05" / "could not check, tried 14:06" / "0.1.9 is available"; a source checkout says to use git and the item is disabled); the check started by hand also pops a tray message with the result; the install item still appears when a release is found. Tested with a real tray menu in a fresh Qt process over three outcomes (up to date, error, release found). This also gives the tray menu texts the four new languages promised in the translations PR. The widget's own QML labels are still pl/en (not part of 0.1.3).
- **03.11.2026** — DIA-63: the Status page opens with one summary row (`js/views/status_summary.js`): Service (the systemd unit's state from DIA-48's dictionary; started by hand it says "Running (not as a service)" instead of a misleading "Stopped"), Agent sandbox, Agents ok/all, Running and Waiting for you — the last two are DIA-51's `counts`. Colour dot per tile (agents: warn when one is down or limited, danger when none works). Seen in QtWebEngine in en/pl/de. New strings in all 7 languages; new file in the precache, SW cache v31.
- **03.11.2026** — DIA-36: direct tests for the five areas (about 135 new tests, none touches the network or a model): `tests/test_assistant_actions.py` (one per action of the table, with the delegates replaced by recorders; yes/no flows; skills; status), `test_release_direct.py` (changelog with real git, itch.io/Steam with fake butler/steamcmd), `test_update.py` additions, `test_persona_direct.py`, a store audit test, and `test_discord_direct.py` (embeds, every button, every slash command, background news, task reports, messages, token errors). Before/after coverage is in the table above. Two of my first assertions were vacuous (`or True`) and were made exact.
- **03.11.2026** — T1, first step (a real bug, own commit): removing `dia.assistant` from mypy's `ignore_errors` list showed that `intent.project` / `intent.prompt` (Optional) went straight to the core for 12 actions. For `debug`, `impact`, `goal`, `scenario` a project-less answer from a model reached `config.project(None)` ("unknown project 'None'"). Now `Assistant._project()` raises `MissingProject` and the assistant asks which project (pl/en, lists the configured ones); a missing prompt falls back to the user's words. Tests for all 12 actions. mypy list: 31 → 30 modules.
- **03.11.2026** — T1, batch 1: ten more modules left the `ignore_errors` list with small fixes (`ui.theme`, `setup`, `release.godot_analysis`, `release.balance`, `knowledge.conversations`, `quality.quality`, `quality.experiments`, `quality.ci`, `skills.builtin`, `cli.tasks`). Two were real (own `fix:` commit): `CIWatcher.poll` used `store.get()` unchecked after the forge call (a task discarded meanwhile crashed the watcher) and `dia comments` did the same for an unknown id. Others were wrong annotations (floats in a `Counter[str]`, a `bool` in a `dict[str, str]`, `[None]` in a list of names).
- **03.11.2026** — T1 done: the `ignore_errors` list went from 31 to **11** modules (target ≤ 15; 106 findings fixed). Batch 2 took nine more (`desktop.appwindow`, `desktop.clipboard`, `sessions`, `work.missions`, `work.goals`, `work.swarm`, `cli.quality`, `cli.work`, `cli.serve`); real problems found were `dia goal review GOAL` on an unknown id and `_keep_index_fresh` assuming every memory backend has `semantic_index` (own `fix:` commit), plus defensive ones (a step without a branch is no longer passed to `git merge`; a swarm check with no scenario result; a clipboard tool without stdin). Left: dia.channels.api.chat, dia.channels.api.settings, dia.channels.api.system, dia.channels.discord.bot, dia.channels.discord.views, dia.channels.voice.audio, dia.desktop.health, dia.skills.integrations, dia.toolchains.godot, dia.voice.audio, dia.work.schedule.
- **03.11.2026** — M1 / M2 prepared, **not done**: `docs/test-reports/2026-11-03-ui-smoke-0.1.3.md` has the automated results (all 9 views × 7 languages render clean with `scripts/ui_smoke.py`; request failures show error states) and the manual checklists for the Qt window + browser (M1) and a real Plasma 6 shell (M2). They need the owner at the computer; M1 and M2 stay ⬜ until the owner ticks the report. `scripts/ui_smoke.py` is new (it runs each language in its own process: QtWebEngine crashes after several runs in one).
- **03.11.2026** — M6: CHANGELOG `[Unreleased]` became `[0.1.3] — 2026-11-03` (regrouped by topic, with the "Internal" paragraph saying that import paths changed and plugin entry points did not; change the date if the tag lands on another day); `scripts/bump-version 0.1.3` and `--check` pass for all nine places; ROADMAP says 0.1.3 is prepared. Not done, on purpose: M1, M2 (need the owner), the tag and publishing (the owner's explicit yes), DIA-01 (after the tag). Release criteria 1, 3 and 4 are met; 2 and 5 wait for the tag and the manual reports.
- **04.11.2026** — M1 / M2 **done** by the owner: the checklists in `docs/test-reports/2026-11-03-ui-smoke-0.1.3.md` were walked through in the Qt window, a browser and a real Plasma 6 shell; everything was fine. One finding on the way: the CLI sessions view listed taken-over sessions before running ones regardless of age, and (on `main`) CI failed on Python 3.11 because a timeout killed only the agent's leader process; both fixed in #53 (`fix:`; helpers of a timed-out agent are now ended with its process group). The changelog's `[0.1.3]` now carries these and the date 2026-11-04. Left: the tag (owner's explicit yes) and DIA-01 (after the tag).
