# Missions and control

## Missions

Give Dia a goal instead of a list of instructions:

```sh
dia mission nova "Przygotuj Nova do zamkniętej rundy testów" --calls 30 --minutes 180
```

or the Missions view in the app, `/mission` on Discord, or just say
"Dia, zorganizuj pracę: ...". Dia:

1. asks the planner agent for steps **with dependencies** (a graph): e.g.
   design → server and UI at the same time → tests and docs;
2. shows you the mission and waits for **Start**;
3. runs every step whose dependencies are done, in parallel (up to
   `max_parallel_tasks`), each as an ordinary task on its own branch built on
   the branches it depends on;
4. when all steps are done, merges the last steps' branches into the
   mission's branch `dia/<mission>` and runs the tests there;
5. waits for your decision: Review, Merge, PR/MR or Discard. Afterwards the
   steps' branches are cleaned up.

Every mission has a **budget** (agent calls and agent minutes); when it is
used up the mission pauses and **Continue** picks it up again (failed steps
get another go). It also has a priority and a log. "Start no more steps"
lets running steps finish; the emergency stop ends them.

```toml
[missions]
planner = "claude"       # default: [plans] planner, then the default agent
max_steps = 6
budget_calls = 30
budget_minutes = 180
step_tests = false       # true: test every step too, not only the result
```

## When something fails: retry policies

```toml
[retry]
agent_errors = 1       # another attempt when an agent fails (crash, timeout)
switch_agent = true    # ... by a different agent
test_fixes = 1         # failed tests go back to the author with the output
delay_seconds = 10

[projects.nova]
retry = { test_fixes = 2 }   # per project
```

All default to 0. A failed attempt's leftover changes are dropped before the
next one; every retry is listed on the task and counts towards a mission's
budget. Usage limits are handled separately (fallback agents, waiting).

## Limits per task

```toml
[task_limits]
minutes = 60          # agent minutes per task, all its calls together
calls = 12            # agent calls per task: retries, reviews and fixes included
agent_timeout = 1800  # seconds per agent call (an agent's own timeout wins)
nice = 10             # CPU priority of agents and tests: 0 normal .. 19 lowest

[projects.nova]
task_limits = { minutes = 120 }
```

All off by default. A task at its limit stops calling agents and fails with
the reason; its branch stays for review. Missions also have their own budget.

## Who takes a task

When you don't name an agent, `[routing]` can choose one:

```toml
[routing]
rules = [{ match = "test|gut|testy", agent = "codex" }]   # regex on the request
auto = true       # else the agent with the best record on this project
min_tasks = 5
```

A rule may name a `project`. The task shows why its agent was picked.

## Rolling back a merged task

**Roll back** on a merged task (or `dia rollback <task>`) prepares its revert
as a new task on its own branch, with the project's tests run. Nothing
changes in your checkout until you merge that task, like any other. A revert
that conflicts with later changes is refused with the command to do it by
hand.

## Mission Control

The Missions view shows every mission as a graph (columns are the order
steps can run in), budget meters, the log, and, when no mission is open,
the live **activity** feed: everything anyone (you, your phone, Discord,
voice, the schedule, the watchers) made Dia do.

## Emergency stop

The red **Stop** button (also on the phone), `/stop` on Discord, "zatrzymaj
wszystko" by voice or chat, or `dia stop`: every running agent and test run
is ended at once (their whole process groups), queued tasks don't start,
missions pause, the schedule and the watchers wait. Dia stays stopped,
across restarts too, until **Resume** (`/resume`, "wznów", `dia resume`).

## Audit log

`dia audit`, or the activity feed: tasks started and finished, merges,
publishing, fixes, discards, accepted facts, note edits, settings and
secrets (names only), devices, schedules, stops, each with who asked for it
(`cli`, `ui`, `device:phone`, `discord:<user>`, `voice`, `schedule:<id>`,
`watch`...).

## Conversation and quiet mode

Dia remembers the last few exchanges of each conversation (each Discord
user, the app, each device), so "a jutro?" after the weather, or "zrób to w
nova" after a question, work. `[assistant] history_turns = 6`,
`history_minutes = 30`.

Quiet mode ("tryb cichy", "możesz mówić", the switch in the sidebar, `dia
quiet on|off`, or a scheduled job at night) makes Dia answer in text only:
a desktop notification instead of speech.

## Memory browser

The Memory view lists Dia's notes (about you, projects, journal), opens and
edits them, searches all notes and shows proposed facts to keep or skip.
Only notes in Dia's own folder of the vault can be opened or changed there.
