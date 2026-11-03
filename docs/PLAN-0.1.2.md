# Plan 0.1.2 — patch after 0.1.1

> Written by Dia on 28.10.2026 (task `20261028-165632-4111`) and kept for the record. 0.1.2 was
> released on 30.10.2026; what it left open moved into [PLAN-0.1.3.md](PLAN-0.1.3.md).

**0.1.1** shipped UI 2.0 and release hygiene (`v0.1.1`, 2026-10-28).
Per [RELEASING.md](RELEASING.md) / SemVer: a patch fixes what that release left
unfinished or broke. **Do not move** `v0.1.1`. **No new epic.**

Source of leftovers: [PLAN-0.1.1.md](PLAN-0.1.1.md) (DIA-01 still open; UI audit
DIA-48–63 unchecked; CLI take-over click-through optional). Work stays in
**Solar9/Dia_DEV**; **Solar9/Dia** stays the public channel.

Sizes: **S** ≈ ½ day, **M** ≈ 1½ day of focused work with agents.

---

## What this patch is for

| Kind | In 0.1.2 | Not in 0.1.2 |
|---|---|---|
| **Fix** | Install/update path bugs from live smoke; status/counter/i18n drift; offline page leftovers; CLI session take-over bugs | New agent/brain features |
| **Improve** | One status dictionary tray/widget/web; Start/Stop/Restart clarity; loading/error/empty; same “working / waiting for you” counts | Redesign of UI 2.0 layout |
| **Add** | Smoke report under `docs/test-reports`; CHANGELOG entries for real fixes only | Landlock, red-team expansion, “product” local brain, `cli.py`/`api.py` split |

---

## Release criteria

1. **DIA-01** done: clean-machine install of public `v0.1.1` (or `0.1.2` candidate) + tray/update path from `0.1.0` and from a pacman install, written up in `docs/test-reports/`.
2. **DIA-48–53** verified on Plasma 6 in PL and EN; failures fixed in this release (or consciously deferred with a CHANGELOG note).
3. **DIA-46 leftover**: one live take-over → reply in Dia → Release back to the terminal (Codex or Cursor), noted in the smoke report.
4. Every must-have meets its criterion; version places say `0.1.2` (`scripts/bump-version --check`); publish only after green CI (never move `v0.1.1`).

---

## Must-have

Order: smoke first (finds the real bugs), then UI consistency fixes, then CLI click-through, then whatever smoke surfaced.

| Status | ID | Title | Pri | Size | Notes |
|---|---|---|---|---|---|
| ⬜ | **DIA-01** | End-to-end release channel check for 0.1.x | P0 | S | Public `Solar9/Dia` + `v0.1.0` assets already confirmed in 0.1.1. Still need: clean install, update `0.1.0`→current, pacman path (no pip), tray “update available”. Report → `docs/test-reports/`. |
| ⬜ | **DIA-48** | One service-status dictionary tray / widget / web, PL+EN | P0 | S | Same labels and colours for Dia/Ollama (and peers) everywhere. |
| ⬜ | **DIA-49** | Start/Stop/Restart: state-dependent buttons, clear confirm, visible result | P0 | S | Settings/desktop services; result already partially in `service-operation.json` — make UI truthful. |
| ⬜ | **DIA-50** | Web: distinct loading / error / empty | P1 | S | Inbox, Tasks, Sesje CLI, Status — no silent blank panels. |
| ⬜ | **DIA-51** | Working agents + “waiting for you”: same counters everywhere | P0 | S | App, tray badge, Plasma widget, Status. |
| ⬜ | **DIA-52** | Task status i18n leftovers | P1 | S | Status filter/options still show raw keys in places (`STATUS_ORDER` in `app.js`). |
| ⬜ | **DIA-53** | Offline “Dia not running” page: theme, title bar, states | P1 | S | Icon + title bar partly done on UI 2.0; finish theme + Start/states. |
| ⬜ | **DIA-46b** | CLI session take-over click-through | P1 | S | Parsing smoke already in `docs/test-reports/2026-10-28-cli-sessions.md`. Finish: take over live terminal → reply → Release. |
| ⬜ | **DIA-65** | Fix regressions found by DIA-01 / UI audit | P0 | M | Bucket for concrete bugs; split into commits as they appear. Empty until smoke runs. |

---

## Nice-to-have (only after must, and only if small)

Triage **DIA-54–63** during the same Plasma review. Ship a fix in 0.1.2 only when it is a clear defect or a half-day polish; otherwise defer with a note.

| ID | Topic | Action in 0.1.2 |
|---|---|---|
| DIA-54 | Window geometry restore | Verify; fix if broken after UI 2.0 |
| DIA-55 | Themes (app / phone / widget sync) | Verify; fix drift only |
| DIA-56 | Accessibility basics | Keyboard/focus on Inbox + Settings |
| DIA-57 | Login / pair form | Verify empty/error states |
| DIA-58 | Plasma widget polish | Badge/count vs app (ties to DIA-51) |
| DIA-59 | Chat polish | No layout regressions from Research-in-composer |
| DIA-60 | Tray menu | Services + update copy still accurate |
| DIA-61 | Status summary | Counters match DIA-51 |
| DIA-62–63 | Remaining UI audit scraps | Defer unless blocking |

---

## Out of scope (later, not a typical patch)

From PLAN-0.1.1 “Later”; do **not** pull into 0.1.2 unless a P0 security hole appears:

- **DIA-28** Landlock as a second sandbox layer
- **DIA-30** Red-team: injection via issues / web / review comments
- **DIA-12–14, 16, 18** “Product” local-brain routing and related brain work
- **DIA-34 / 35** Split `cli.py` / `api.py`
- **DIA-20 / 21** Live review pass, physical phone validation
- New milestones or capability-map rows

---

## Recommended sequence

1. **Smoke DIA-01** on a clean machine (or VM) against published `v0.1.1` — write the report even if everything passes; file bugs into DIA-65.
2. **Plasma 6 walkthrough** of DIA-48–53 (and skim 54–63) in PL and EN; fix mismatches.
3. **CLI take-over** (DIA-46b); append to the CLI sessions smoke note.
4. Land DIA-65 fixes; `scripts/bump-version 0.1.2`; CHANGELOG `## [0.1.2]`; tag only after green CI.
5. Re-run a short install/update smoke on the published `v0.1.2` assets.

---

## Decisions for you

1. **Scope freeze** — agree that 0.1.2 is patch-only (table above). Anything epic-sized waits for an unplanned next minor.
2. **Smoke owner** — DIA-01 needs a real Plasma box (or disposable VM); agents cannot finish it alone.
3. **Defer policy** — if DIA-54–63 are mostly already fine on UI 2.0, mark them ✅ in the smoke report without code churn.

---

## Work log

- **28.10.2026** — this plan: carry DIA-01 + UI audit + CLI click-through from 0.1.1; explicit non-goals for Landlock / red-team / local brain / cli–api split.
