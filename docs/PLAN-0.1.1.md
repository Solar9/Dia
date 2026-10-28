# Plan 0.1.1 — backlog and progress

Source: [Grok analysis](https://dia-analiza-backlog-i-roadmapa-0-3-0-i3cb.pages.grok.bot/)
(PDF: `~/Pobrane/Dia — backlog i plan 0.1.1.pdf`, checked 28.10.2026 on main `8e6e13b`).
Plan 0.1.1 replaces the old 0.2.4 plan. Work lives in **Solar9/Dia_DEV**;
**Solar9/Dia** is only the public release channel.

**Next release after 0.1.0:** UI 2.0 (ready on `ui_v2.0`, waiting to ship) +
bugfixes and release hygiene. Must ≈ 6 days; nice ≈ 5.5 days after must.

Sizes: **S** ≈ ½ day, **M** ≈ 1½ day, **L** ≈ 3+ days of focused work with agents.

Progress notes below are updated as work lands on `ui_v2.0` / main.

---

## Release criteria (0.1.1)

1. Every must-have meets its criterion, or is consciously deferred with a note in CHANGELOG.
2. `publish.yml` publishes `v0.1.1` only after green CI (3.11, 3.13, **3.14** + Qt job) on the tagged commit; published tags are never moved (fix → 0.1.2).
3. All 9 version places say `0.1.1`, checked by a test.
4. One live Plasma 6 review in `docs/test-reports`: install/update from 0.1.0 and from old 0.2.x (DIA-01, 47), plus UI services/counters/errors/offline (DIA-48–53) in PL and EN.

---

## Must-have

Order from the plan: CI gate + single version source first (DIA-02, 09, 10, 07),
then updater (DIA-47, 06, 01), then docs (DIA-15, 38). DIA-64 (UI 2.0) is the
main ship item.

| Status | ID | Title | Pri | Size | Notes |
|---|---|---|---|---|---|
| ✅ | **DIA-64** | Ship UI 2.0 in 0.1.1 | P0 | S | Merged via [#33](https://github.com/Solar9/Dia_DEV/pull/33); version bumped to 0.1.1. Live Plasma smoke / DIA-48–63 checklist still useful in `docs/test-reports`. |
| ✅ | **DIA-02** | Publish only from a green-CI commit; never move release tags | P0 | S | Done 28.10 on `ui_v2.0`: `publish.yml` runs test matrix + Qt job before publish; `docs/RELEASING.md`; `publish-release.sh` refuses moving an existing tag. |
| ✅ | **DIA-09** | One version source (pyproject, Android, npm, …) | P1 | S | Done 28.10: `scripts/bump-version` (+ `--check`); `tests/test_version.py`; publish-release runs `--check`. PKGBUILD stays `@VERSION@`. |
| ✅ | **DIA-10** | Python 3.14 in CI matrix | P1 | S | Done 28.10: CI matrix `3.11`, `3.13`, `3.14`. |
| ✅ | **DIA-07** | Qt window/tray tests in CI (PySide6, offscreen) | P1 | M | Done 28.10: `qt` job installs `.[dev,qt]` and runs `tests/test_appwindow.py` offscreen (also required by publish). |
| ✅ | **DIA-47** | Old 0.2.x installs must never see 0.1.x as an update | P1 | S | Done 28.10: choice **(a)** — `update.newer()` treats pre-reset 0.1.0–0.2.3 as older than any ≥0.1.1. |
| ✅ | **DIA-06** | Updater must not `pip install` on a pacman install | P1 | S | Done 28.10: `system_package()`; tray copy + `install()` refuse pip and point at `pacman`. |
| ⬜ | **DIA-01** | End-to-end release channel check for 0.1.x | P1 | S | Solar9/Dia is **public**; `v0.1.0` has wheel, tarball, installers, PKGBUILD, SHA256SUMS (checked 28.10). Still needs clean-machine install + tray update smoke → `docs/test-reports` after 0.1.1 exists. |
| ✅ | **DIA-15** | Docs/UI still recommend qwen2.5:3b (scored 2/5) | P1 | S | Done 28.10: recommend **qwen3.5:4b** (8/9, 25.10.2026) in ASSISTANT.md, `dia.example.toml`, app.js EN/PL default. |
| ✅ | **DIA-38** | Docs drift: ROADMAP “Next”, UI.md phone, ARCHITECTURE | P2 | S | Done 28.10: ROADMAP → 0.1.1 + link to this plan; UI.md points at MOBILE.md; ARCHITECTURE covers Qt window, tray, CLI sessions. |

---

## Nice-to-have (only after must)

| Status | ID | Title | Pri | Notes |
|---|---|---|---|---|
| ✅ | DIA-03 | Protect `main` + pre-commit ruff | P1 | Pre-commit + CONTRIBUTING done. Branch protection skipped (private repo needs GitHub Pro) — left as-is 28.10. |
| ✅ | DIA-08 | Name flaky test (JUnit in CI) | P2 | Done 28.10: `--junitxml` + artifacts; Qt tray test renamed `test_qt_offscreen_window_hides_to_the_tray`. |
| ✅ | DIA-11 | Guard: merge/push requests never become `run` | P1 | Done 28.10: `guard_irreversible()` after every brain; prompt example; tests. |
| ✅ | DIA-25 | Plasma widget: deprecated `onExpandedChanged` inject | P2 | Done 28.10: use `root.expanded` / `root.refresh()`. |
| ✅ | DIA-26 | Wake-word copy conflict (Hey Jarvis vs Hej Dia) | P2 | Done 28.10: docs/README/voice advertise **Hej Dia**; Jarvis kept only as ASR alias. |
| ✅ | DIA-27 | `.desktop` has two main Categories | P3 | Done 28.10: `Categories=Utility;` (desktop.py + PKGBUILD). |
| ✅ | DIA-29 | Loud warning when agents run without sandbox | P1 | Done 28.10: `WARNING` on `dia serve`; `SECURITY` log when an agent runs with `sandbox=None`. |
| ✅ | DIA-40 | Move validation logs out of user docs (UI.md) | P3 | Done 28.10: → `docs/test-reports/2026-10-26-desktop-validation.md`. |
| ✅ | DIA-46 | CLI session takeover with real Codex + Cursor | P2 | Done 28.10: filters + pending UX; smoke note `docs/test-reports/2026-10-28-cli-sessions.md` (full take-over click-through still optional). |

---

## Later (out of 0.1.1 checklist)

DIA-04, 05, 12–14, 16–24, 28, 30–32, 34–37, 39, 41–45, and UI audit
DIA-48–63 (checked during DIA-64 smoke; many may already be fixed on `ui_v2.0`).

Highest later items called out by the plan: Landlock (28), red-team issues/web/review (30),
live review (20), physical phone (21), local-brain routing (12–14, 16, 18),
cli.py/api.py split (34/35).

### UI audit checklist (verify with DIA-64 smoke)

| ID | Topic | On `ui_v2.0` (28.10) |
|---|---|---|
| DIA-48 | One service-status dictionary tray/widget/web, both languages | unchecked |
| DIA-49 | Start/Stop/Restart: state-dependent buttons, clear confirm, visible result | unchecked |
| DIA-50 | Web: distinct loading / error / empty | unchecked |
| DIA-51 | Working agents + “waiting for you”: same counters everywhere | unchecked |
| DIA-52 | Task status i18n leftovers | unchecked |
| DIA-53 | Offline “Dia not running” page: theme, title bar, states | partly (icon + title bar landed earlier on branch) |
| DIA-54–63 | Window geometry, themes, a11y, login form, widget polish, chat, tray menu, Status summary | unchecked |

---

## Decisions for you (from the plan)

1. ~~DIA-47~~ — chose **(a)** in code.
2. ~~DIA-01~~ — Solar9/Dia public + v0.1.0 assets confirmed; live smoke after tag.
3. ~~DIA-02~~ — documented in RELEASING.md (no tag moves).
4. ~~DIA-11~~ — code guard landed; say if you still saw merge→run live before.
5. ~~DIA-03~~ — branch protection skipped (private + no Pro); pre-commit stays.
6. ~~UI 2.0 PR~~ — [#33](https://github.com/Solar9/Dia_DEV/pull/33).

---

## Work log

- **28.10.2026 — UI polish on `ui_v2.0` (toward DIA-64 / DIA-46)**
  - Research moved from Status → Inbox/Tasks composer (option C).
  - Settings: side nav in four groups; Appearance = themes only; Desktop & services / Security separated.
  - Inbox: fluid width (no fixed max-width).
  - CLI: new session shows pending until first agent reply; longer wait; no minute-limit wait for `cli-session`.
  - Transcripts: strip Codex AGENTS.md + env; drop Cursor auto-context turns; keep only `<user_query>`.
  - Docs: ASSISTANT.md / UI.md updated for Research + Settings layout.
- **28.10.2026 — this file** added so progress can be tracked in-repo.
- **28.10.2026 — must hygiene on `ui_v2.0`**
  - DIA-15 / DIA-38 docs+recommendation; DIA-09 bump-version + test; DIA-10 + DIA-07 CI jobs;
    DIA-02 publish gate + RELEASING.md.
  - DIA-47 (a) + DIA-06: updater treats pre-reset 0.2.x as older than ≥0.1.1; pacman installs
    never `pip install`.
  - DIA-64: opened PR #33. Remaining musts: green CI + smoke (48–63), DIA-01 after tag.
  - Nice-to-have: DIA-08/11/25/26/27/29/40/46 done in code; DIA-03 pre-commit added
    (branch protection still a GitHub setting).
