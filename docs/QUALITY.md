# Quality guards

Tests answer "does it still work". These answer "is it still the code you
want": rules of the architecture, assumptions an agent made, debt piling
up, and bugs whose cause nobody has proven.

## Architecture rules

```toml
[projects.nova]
architecture = "ARCHITECTURE.md"          # the default (also docs/ARCHITECTURE.md)
architecture_forbid = [
  { from = "ui/**", to = "data/**", why = "UI never talks to the data layer directly" },
  { from = "scenes/**", to = "autoload/save*.gd", why = "only the game state saves" },
]
```

- **Forbidden dependencies** are checked on every change, statically: a
  file the task changed that matches `from` and uses a file matching `to`
  (Godot `ext_resource`, `preload`/`load`, a `class_name` by name, an
  autoload; in other languages a file named in the code; the same graph as
  `dia impact`).
- **Rules in prose** (the architecture file) go to the reviewer with the
  diff. For each rule the change breaks it writes
  `VIOLATION: <rule>: <where>` and requests changes. A later review round
  that finds none clears them.

A violation blocks merging:

```
dia merge 20261025-1200-ab12
error: blocked by the quality guards:
- architecture: UI never talks to the data layer directly (ui/menu.gd uses data/store.gd)
dia merge 20261025-1200-ab12 --override "read-only access, agreed for the prototype"
```

In the UI, Merge asks for the override. The override is a decision in the
log (`dia why` finds it).

## Verification gate

After a large change (150 changed lines or more; `[verification] always =
true`, globally or per project, for every change), the agent that wrote it
is asked, read-only, which assumptions its change rests on, each with a
command that exits 0 when the assumption holds:

```
✓ store.gd has load()          $ grep -q "func load" data/store.gd
✗ saves are JSON               $ grep -q JSON data/store.gd
```

Dia runs the commands itself, in the sandbox, in the task's worktree. The
task records how many held. Self-reported confidence is not asked for:
what counts is how many assumptions survived a check. A failed check
blocks merging like a violation (fix it, or override with a reason).

```toml
[verification]
min_lines = 150
max_checks = 5
timeout = 300
# enabled = false
```

## Technical debt register

```
dia debt nova
  1. [ 8.4] long function: player/player.gd: _physics_process() at line 40: 140 lines, changed 9x
  2. [ 6.0] no tests: player/dash.gd: changed in 5 commits lately, no test names it, changed 5x
  3. [ 3.5] duplication: ui/inventory.gd: 6 duplicated blocks with ui/shop.gd
dia debt nova --fix 1
```

Read from the project, no agent involved: long functions, deep nesting,
large files (GDScript and Python for functions; any code for size),
duplicated blocks, files changed often lately that no test names, and
vulnerable dependencies (`--deps`: pip-audit or npm audit, as in the
security report). The score is benefit × severity ÷ cost:

- the benefit is how often the file changed in the last six months, since
  debt in code you keep touching costs you every time;
- the cost is roughly how much code a fix touches.

`--fix N` (or the Fix field per project in Status) is an ordinary task: an
agent refactors the item without changing behaviour, the tests run, and you
review and merge.

```toml
[debt]
function_lines = 60
nesting = 5
file_lines = 600
duplicate_lines = 6
```

## Debugging swarm

```
dia debug nova "po dashu postać czasem przelatuje przez ścianę"
1. [confirmed] speed not clamped after a dash (player/physics.gd:move); from claude (logs), codex (code)
2. [ruled out] input repeat on dash (player/input.gd:_input); from claude (history)
Confirmed by a failing test: speed not clamped after a dash. Fix it from its test's branch: dia debug --fix 20261025-1300-cd34
```

1. Agents work on the bug in parallel, read-only, each in a role:
   - *logs*: error output, log files, test runs;
   - *code*: the code paths involved;
   - *history*: recent commits that touched them.

   Each proposes up to three causes. Causes at the same place are merged,
   and the most backed come first.
2. The top ones (`[debug] max_checks`, default 3) each become a test
   scenario: a test that passes if the code behaves correctly there and
   fails if the cause is real. Dia runs it. Failing confirms the cause and
   passing rules it out. How many agents proposed a cause does not decide
   anything.
3. `dia debug --fix ID` (the button on the task) fixes the first confirmed
   cause, starting from the branch with its test, so that test guards the
   fix.

You can also start it with "Dia, znajdź, czemu postać przelatuje przez
ścianę w nova", the form in Status, or `POST /api/debug`.
