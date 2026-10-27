# Goals and context

## Goals over weeks

```
dia goal new uv "Starfall do Early Access" --weeks 8
goal 20261025-1400-ab12
Starfall do Early Access  [active], by 2026-12-20
  [ ] 1. Saving and loading work in every level
  [ ] 2. The Steam page is ready
  [ ] 3. Two weeks of playtests without a crash
```

A planner agent looks at the project, read-only, and breaks the goal into
milestones. Each milestone has a "done when". Once a week (`dia serve` does
it by itself; `dia goal review ID` any time) Dia reviews the goal. The
review covers:

- the missions and tasks done for it;
- blockers: failed work, rollbacks, benchmark regressions, security
  incidents;
- the commits of the week.

It proposes which milestones are now reached and the next mission. Nothing
starts by itself. `dia goal approve ID` (or the button in the Missions view)
marks the milestones and prepares the mission, which you start like any
mission. `dia goal list` shows where everything stands, and `dia goal close
ID` ends a goal.

You can also say: "cel: Starfall do Early Access w 8 tygodni".

```toml
[goals]
review_days = 7
planner = "claude"     # default: [missions] planner, then the default agent
```

## Plan simulation

Every plan and mission shows, before it runs:

```
Likely files: player/dash.gd, ui/hud.gd, player/movement.gd
Expected: ~24 agent minutes, 2 call(s) (up to 6 with retries; from 31 past tasks)
Risks: player/dash.gd: 2 earlier change(s) rolled back or made a benchmark worse; no tests among the likely files: consider a scenario first
Waits for you: you accept the plan (nothing runs before); you review and merge each finished step
```

How each part is found:

- **Likely files**: files the plan names; files that match its words (as
  `dia impact` matches them); files that past tasks about the same things
  changed.
- **Expected cost**: each step's agent's average minutes on this project,
  and the agent calls, with the retries your policy allows.
- **Risks**:
  - earlier rollbacks or regressions in those files;
  - technical debt there;
  - architecture rules in play;
  - no tests;
  - a change big enough for the verification gate.

No agent runs for this. Voice says only the plan; the app, the CLI and
Discord show the rest.

## Work profiles

```toml
[profiles.starfall]
project = "uv"
apps = ["godot4 --editor --path ~/games/uv", "code ~/games/uv"]
names = ["starfall", "ultra"]
```

"Zaczynam pracę nad Starfall" (or `dia work start ultra`, or the Work
card in Status) opens the apps and tells you where you are:

- your note from last time;
- the last tasks;
- what waits for your review;
- the goal and its latest review.

"Kończę na dziś, zapisz że skończyłem na dashu" (or `dia work stop --note
"..."`) saves the session: your note, what was done and merged, what still
waits, uncommitted files, the last things you talked about. Every project
works as a profile too, just without apps. Only the commands you configured
start, and nothing about what you do in them is recorded.

## One conversation across devices

The desktop UI, your paired phone, voice and your Discord account are one
conversation. Ask on the phone, follow up at the desk, or say "tak" by
voice to a plan you asked for on Discord. The recent turns and the plan
waiting for your "yes" are kept in Dia's data directory, so they survive a
restart. Other people (another Discord user, a guest voice) keep their own
conversations.

```toml
[assistant]
one_conversation = true
owner_ids = ["123456789012345678"]   # your Discord user id, your speaker name
```

### Chat sessions

Besides that main conversation, the app's Chat holds separate
conversations, like threads: "+ New conversation", then rename (✎) or
delete (×). Each one has:

- its whole history, stored by Dia (so it survives a reload and shows on
  every device of yours);
- its own context for follow-ups, not forgotten after a pause;
- its own plan waiting for a "yes".

The main conversation is the one voice, the phone notifications and
Discord continue. Deleting it only clears its history. API:
`GET/POST /api/sessions`, `GET/PATCH/DELETE /api/sessions/{id}`, and
`session` in `POST /api/chat`.

## Discreet suggestions

Dia looks only at its own history: tasks, the decision log, the debt
register, goals, and git. It never looks at what you do on the computer.
From that it suggests:

- "2 rollbacks or regressions in nova/combat/ this week: analyse what they
  have in common?"
- "Tests failed in 4 tasks on nova this week: look for flaky or broken tests?"
- "player.gd changed 9x lately and has a long function: pay it off?"
- "3 finished tasks have waited 3+ days for your review."
- a goal review waiting for your approval.

The limits:

- at most `per_day` suggestions a day (default 1);
- the same one not again within `repeat_days` (default 14);
- a dismissed one never again;
- they go out like any notification, so quiet hours and the notification
  budget hold them back.

Accepting one runs a read-only analysis or a debt task, never a merge.
Find them with `dia suggestions` (`--check`, `--accept KEY`, `--dismiss
KEY`) or in the Status view.

```toml
[suggestions]
enabled = true
per_day = 1
repeat_days = 14
```

## Self-check

In `dia serve`, each channel and watcher (Discord, voice, the UI, CI,
schedules, goals, suggestions...) runs supervised:

- One that crashes is restarted after 5 s, then a growing pause up to 5
  minutes, instead of stopping Dia.
- The audit log records each restart, and you get a notice on the first
  one, then only if it keeps happening.
- `/api/health` and the Status view show what is restarting and why.
- Tasks that were running when Dia stopped are recorded as interrupted when
  it starts again.

`dia doctor --fix` repairs what is safe and reports what it cannot fix:

- removes worktrees left behind by finished, discarded or vanished tasks,
  and stale benchmark copies;
- moves a broken memory index aside and rebuilds it;
- restores private permissions on Dia's data directory and secrets file.

Every repair is in the audit log.
