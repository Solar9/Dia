# Experiments and measurement

Numbers from tests and benchmarks beat a model's confidence. This page covers
how Dia measures your projects, its agents and itself.

## Benchmarks per project

Give a project a command that prints numbers:

```toml
[projects.nova]
path = "~/games/nova"
benchmark = "godot --headless --path . res://bench/bench.tscn"
benchmark_runs = 3                       # the median of three runs
benchmark_better = { fps = "higher" }    # default: lower is better
benchmark_tolerance = 0.05               # changes under 5 % are noise
# benchmark_timeout = 1800
```

The command prints its metrics either as one JSON object on a line
(`{"frame_ms": 12.4, "load_s": 1.8}`) or as lines like `frame_ms: 12.4` or
`fps=144`. It runs on a clean, detached copy of the commit, in the sandbox,
like the tests.

- `dia bench nova` measures the base branch and compares it with the last
  result; `--ref BRANCH` measures another commit; `--history` lists results.
- After every merge Dia measures the base branch again. A metric that got
  worse beyond the tolerance is reported (an alert with the commits that
  came in, an audit entry `benchmark.regression`) and counts against the
  agent that wrote the merged task.
- `GET /api/projects/nova/benchmarks`; the **Benchmark** button on the
  project in Status.

## Experiments

"Would rewriting the inventory as ECS make nova faster?" Instead of an
opinion, Dia tries it:

```
dia experiment nova "rewrite the inventory as ECS: is it faster?" \
    --approach "ECS" --approach "keep the nodes, cache lookups"
dia experiment nova "speed up pathfinding" -a claude -a codex
```

or say "Dia, sprawdź, czy przepisanie ekwipunku na ECS przyspieszy nova",
or use the **Experiment** form in Status.

Each variant is an ordinary task on its own branch (one per agent, or one
per approach, by the default agent): written in the sandbox, tested, then
benchmarked. The experiment (a task with mode `experiment`) holds a table:

| variant | agent | status | tests | change | frame_ms |
|---|---|---|---|---|---|
| base | - | - | - | - | 10 |
| 1 (ECS) | claude | done | ok | +420/-310 | 7 (-30%) |
| 2 (cache lookups) | claude | done | ok | +40/-5 | 9 (-10%) |

and a recommendation: the variant with passing tests that improves the most
metrics (and makes fewer worse), the smaller change on a tie. Nothing is
merged: merge the variant you want like any task and discard the rest.
Without a benchmark the variants are compared by tests and size only.

```toml
[experiments]
max_variants = 3                 # each variant is an agent call (plus retries)
agents = ["claude", "codex"]     # default variants when none are given
```

## Dia's scorecard

Is Dia getting better? `dia scorecard` (also the Usage view and
`/api/scorecard`) shows, per week: coding tasks, the share finished, discarded
work, merges rolled back, how often a retry rescued a failing task, review
rounds per reviewed task, minutes per task, sandbox incidents and benchmark
regressions. The last week against the ones before is the answer.

## Agents judged by quality

`dia usage` and the Usage view show, per project and agent, besides the
success rate a **quality** score: the share of tasks done and still
standing (not rolled back, no benchmark regression), less 10 points for
every review round above one on average. Proposals to change a project's
default agent and automatic routing (`[routing] auto = true`) use it, so an
agent that finishes everything but whose merges come back out loses to a
careful one. Proposals still wait for you to apply them.

## Shadow brain

Every request the assistant understood is kept locally (the text, the
action, the project, the skill, which brain decided; `[assistant]
log_intents = false` turns it off). Before trusting a new brain (a local
model, a new prompt):

```
dia brains --replay 50 --brain local
local: agrees on 46/50 (92%); same action 48, errors 1
  "popraw menu w nova": was run nova, now ask nova
```

The candidate only interprets; nothing is executed. Requests are replayed
without the conversation around them, so follow-ups may legitimately differ.
