# Dia architecture

## Principles

1. **Nothing vendor-specific in the core.** The core knows about *agents*,
   *projects* and *tasks*. Claude, Codex, GitLab, Godot, Discord, Whisper are
   all plugins, selected in the config file.
2. **Built-ins are plugins too.** Built-in plugins are registered through the
   same Python entry points that a third-party package would use. If the core
   needs a special case for a built-in, the plugin API is missing something.
3. **Isolation by default.** Every task runs in its own git worktree on its own
   `dia/<task-id>` branch. Agents never touch your checkout.
4. **Humans own irreversible actions.** Dia may read, analyse, edit and commit
   on task branches. Merging, pushing, deploying, deleting and sending
   messages to other people require explicit approval.
5. **Works on modest hardware and plans.** Subscription-logged CLIs instead of
   API keys; local speech models sized for a laptop CPU; cheap paths
   (no LLM call) for simple commands, to save usage limits.

## Layers

```
 interfaces   terminal (now) · Discord · local voice · web panel      dia.channels
     │
 brain        understands requests, plans, picks agents                dia.brains
     │
 core         orchestrator · task store/memory · permissions
     │
 execution    agents ──────── workspaces (git worktrees)               dia.agents
              toolchains (test/build per stack) · forges (MR/PR)       dia.toolchains, dia.forges
```

Every interface calls the same core API (`Orchestrator`), so a feature added
to the core is available from the terminal, Discord and voice at once.

## Extension points

| Group            | Contract                                    | Status   | Examples                         |
|------------------|---------------------------------------------|----------|----------------------------------|
| `dia.agents`     | `dia.agents.Agent.run(AgentRequest)`         | done     | claude-code, codex, cursor, command |
| `dia.memory`     | `Memory.context_for(project, task)`, `Memory.record(project, report)`, `Memory.search(query)` | done (optional) | markdown / obsidian vault |
| `dia.channels`   | `Channel.run()`: receive requests, report, ask for approvals | done | discord, voice (terminal is the CLI) |
| `dia.stt`        | `SpeechToText.transcribe(audio, language)`   | done     | faster-whisper, command (whisper.cpp...) |
| `dia.tts`        | `TextToSpeech.synthesize(text, output)`      | done     | piper, command (espeak-ng, spd-say...) |
| `dia.wake`       | `WakeWord.detect(chunk) → bool`              | done     | openwakeword                     |
| `dia.brains`     | `Brain.interpret(text, ctx) → Intent`        | done     | rules, agent (Claude/Codex/Cursor), openai/ollama (local or cloud) |
| `dia.toolchains` | `test(workdir)`, `context(workdir)`, `launch(workdir)` | done | godot |
| `dia.forges`     | `Forge.publish(repo, branch, base, title, body)`, `issues(repo, label)` | done | git, github (gh), gitlab (glab / push options) |
| `dia.skills`     | `Skill.run(args) → str` (+ `description`, `args` for the brain) | done | weather, news, stocks, briefing |

A project's `test_command`, when set, always wins over the toolchain's test.

### Writing a plugin

An agent for some new CLI:

```python
# my_dia_plugin/agent.py
from pathlib import Path
from dia.agents import AgentRequest, AgentResult, CliAgent, Mode


class MyAgent(CliAgent):
    kind = "my-agent"
    default_command = "my-agent"

    def build_argv(self, request: AgentRequest, scratch: Path) -> list[str]:
        flag = "--readonly" if request.mode is Mode.READ_ONLY else "--write"
        return [self.command, flag, request.prompt]

    def parse(self, request, scratch, exit_code, stdout, stderr) -> AgentResult:
        return AgentResult(
            agent=self.name,
            success=exit_code == 0,
            summary=stdout.strip(),
            exit_code=exit_code,
            error=stderr or None,
        )
```

```toml
# my_dia_plugin/pyproject.toml
[project.entry-points."dia.agents"]
my-agent = "my_dia_plugin.agent:MyAgent"
```

Then, in the user's `dia.toml`: `[agents.mine]` with `type = "my-agent"`.
Every key other than `type` is passed to the plugin as `self.options`.

For a one-off CLI, no code is needed at all: use `type = "command"` with an
`argv` template.

## Task lifecycle

```
request → queue (max_parallel_tasks) → worktree + branch dia/<id>
        → (memory: notes as context) → agent.run() → commit (if changes)
        → test_command → record in SQLite (+ memory journal) → report
        → (human, any channel) diff → merge / discard
```

Read-only tasks run in a worktree as well (so a misbehaving agent cannot
modify your checkout); it is removed afterwards. Edit tasks that produced
no changes are removed together with their branch.

## Cross-review

`Orchestrator.review_task` (also run after a task with `review=True` or
`[review] auto`): a reviewer agent, by default any agent other than the
author, gets the task and the diff in its prompt, read-only, and answers
starting with `VERDICT: APPROVE` or `VERDICT: CHANGES_REQUESTED`. On changes
requested, the author gets the findings, its fix is committed, tests rerun
and the reviewer looks again, up to `fix_rounds`. Every round is kept in the
task's `details["reviews"]`. Putting the diff in the prompt means any agent
can review, including ones that cannot run commands read-only.

## Plans

A task is a list of steps; an ordinary task is one step. `create_plan` builds
the steps from a `[pipelines.<name>]` recipe or asks a planner agent
(read-only, in a scratch worktree) for a JSON plan, validated against the
configured agents, and stores it as a task with status `planned`. `run_plan`
runs the steps in order in one worktree: each agent gets the goal, the
earlier steps' summaries and its own instruction; Dia commits after every
step and stops at the first failure. The last agent that committed is the
task's `author`, who receives review and CI findings.

## Usage limits

Subscription CLIs stop when the plan's limit is used up. `CliAgent` flags a
failed result whose error or short answer matches a limit message
(`dia.limits.LIMIT_PATTERNS`) and parses the reset time when the message has
one (Claude's `|<epoch>`, "in 3 hours", "at 5:00 PM"). `Orchestrator.call_agent`,
used for every agent call (steps, reviews, fixes), then marks the agent in
`<data_dir>/limits.json` (shared by all Dia processes), emits a `limit`
event and gives the request to the next `[limits] fallback` agent that is not
limited (a review never falls back to the author). When all are limited, the
task becomes `waiting` until the soonest reset, up to `max_wait_hours`.
Which agent finally did a step is in the step record and `details.fallbacks`.

## Toolchains

`toolchain = "auto"` (default) asks each installed toolchain plugin whether
it recognises the project. The toolchain adds project facts to every agent's
context, tests a worktree when there is no `test_command`, and launches the
project from your checkout. The Godot toolchain copies the checkout's
`.godot/` import cache into the worktree so tests don't re-import everything,
and treats script errors in the output as failures.

## CI feedback

`Forge.ci_status` / `Forge.ci_log` read a branch's pipeline (`gh pr checks`
and `gh run view --log-failed`; `glab ci get` and `glab ci trace`). In
`dia serve`, `CIWatcher` polls published tasks whose CI is pending and emits
`Event("ci", ...)` to every channel listener (`Orchestrator.listeners`).
`Orchestrator.fix_ci` re-attaches a worktree to the task branch, gives the
author the failed jobs and log, commits and pushes, which updates the open
pull/merge request, and marks CI pending again.

Review comments follow the same path: `Forge.review_comments` reads reviews,
conversation comments and inline notes (`gh pr view` / `gh api`, `glab api`
notes), the watcher emits `Event("review", ...)` for new ones (bots are
ignored), and `Orchestrator.address_comments` hands them to the author and
pushes the result.

## Project watcher

`ProjectWatcher` (in `dia serve`, with `[watch]`) polls the watched branch of
each project. The first look only records the commit; every later new commit
is tested by `Orchestrator.check_commit` in a detached worktree, with the
same test as tasks (`test_command` or the toolchain), and recorded as a task
with mode `check`. A failure emits `Event("watch", check, "failed")`; the
next passing commit emits "fixed". `fix_build` turns a failed check into an
ordinary edit task whose prompt holds the commit and the test output, so the
fix goes through the usual review and merge approvals.

## UI and API

`ApiChannel` (aiohttp) runs inside `dia serve` on 127.0.0.1: a JSON API over
the same core calls the other channels use, a WebSocket that pushes task
updates (`TaskStore.listeners`) and events (CI, review, voice state), and the
static web UI (Preact + htm, vendored, no build step). The desktop app is that
UI in a pywebview window; the KDE widget is QML using the same API. Auth is a
local token plus a Host-header check.

The same UI is an installable PWA (manifest, service worker caching only the
app shell) with a phone layout. With `[ui] remote = true`, requests for the
`[ui] hosts` names (e.g. through `tailscale serve`) are accepted with the
token of a paired device (`dia.devices`, hashes in `devices.json`), never
the owner token; devices are refused the configuration, the microphone and
device management. See docs/MOBILE.md.

## Persona, skills and settings

`dia.persona` turns `[assistant]` (name, user name, personality) into a
paragraph added to every model prompt. Skills are plugins the brain picks
with the `skill` action (or the rule brain, for fixed phrases);
`Assistant.run_skill` runs them. Settings saved in the UI go to
`settings.json` beside the config file and are merged over it at load
(`config.merge`); `Orchestrator.apply_config` switches to the new
configuration without a restart, and each `Assistant` rebuilds its brains
when it notices the change.

## Schedule, push, issues

`dia.schedule.Scheduler` runs in `dia serve`: every minute it runs the jobs
whose cron matches (from `[[schedule]]` and `schedules.json`) and emits a
`schedule` event with the answer. `dia.push.Push` listens to events and
task saves and sends Web Push messages (VAPID key in `vapid.pem`) to the
subscribed devices. `dia.issues.IssueWatcher` imports labelled issues as
planned tasks through `Orchestrator.import_issue`; they run only on
approval.

## Missions and control

`dia.missions.Missions` keeps a mission as a task with `mode = "mission"`
and its step graph in `details.mission`; `Orchestrator.run_plan` hands such
tasks to it. Each step is an ordinary `run_task` with `start_from` (the
branch to build on) and `details.mission/step`; several dependencies are
merged into a helper branch first. The integrated branch makes the mission
reviewable, mergeable and publishable through the usual calls. See
docs/MISSIONS.md.

`dia.processes` registers every agent and test process (own process group);
`Orchestrator.stop_all` ends them and sets `halted` (in `state.json`), which
`_ensure_running`, the queue, missions, the scheduler and the watchers
respect. `dia.audit.ACTOR` (a context variable set by each channel) names
who asked for an action; `Orchestrator.audit` writes it to the `audit`
table, and the API streams new entries to the UI.

## Usage

`Orchestrator.call_agent` logs every agent call (purpose, duration, outcome,
limit) to the `usage` table; `TaskStore.usage(days)` aggregates it for the
UI and `dia usage`.

## Brains

A brain turns a free-form message into an `Intent`: `run` (edit task), `ask`
(read-only task), `status`, `tasks` or `chat` (an answer or a clarifying
question). Brains are tried in the configured order until one answers, so a
free rule-based brain handles fixed phrases, a local model handles the rest
and a subscription model can be the fallback. Every model answer is validated
against the configuration: unknown projects or agents never get through.

A brain cannot merge, discard or delete; those stay explicit approvals.
`Assistant` executes intents and is shared by every natural-language channel
(`dia say`, Discord messages, voice).

## Memory

Memory is optional: without a `[memory]` section Dia behaves exactly the same.
Two kinds of data are kept apart:

| What | Where | Why |
|------|-------|-----|
| Knowledge: profile, project notes, decisions | memory backend (Markdown / Obsidian vault) | written and corrected by a human |
| Operational data: task history, results | SQLite | lots of machine data |

The Markdown backend writes only inside its own folder of the vault. It
creates missing project notes from a template and appends to a daily
journal; it never rewrites a note a human may have edited.

For each task it also searches notes for excerpts related to the request
(keyword search with prefix matching, no index; semantic search can be a
later backend option). The search scope is the Dia folder by default and
can be widened to the whole vault, minus `exclude` patterns, hidden folders
and notes marked `dia: private`. Everything that reaches the context is sent
to the agent running the task. `dia memory search "<query>"` shows what an
agent would get. Memory errors are reported as warnings and never fail a
task.

### Learning

With `[memory] learn = true`, `Orchestrator.learn` runs in the background
after a successful task: a read-only, tool-less agent call (`learn_agent`,
`learn_model`) gets the request, the outcome, the changed files and the
current notes, and answers with at most three lasting facts as JSON. They
are kept as proposals in the task (`details.learn`) and announced with a
`learn` event. Only a person's decision (`decide_facts`: UI, Discord, `dia
learned`) writes them, through `Memory.remember`, which the Markdown backend
implements by appending to the project note's "Learned by Dia" section.

## Permission levels

| Level | Without asking                                   |
|-------|--------------------------------------------------|
| 🟢    | read code, analyse logs, read-only agent tasks, run tests |
| 🟡    | edit and commit inside a task worktree/branch    |
| 🔴    | merge, push, open MR/PR, delete, deploy, message other people: always asks |

Approvals are explicit calls on the core (`merge_task`, `discard_task`), made
only when a person asks: `dia merge` in the terminal or a button in Discord.
Merging refuses to run if the checkout is on another branch and aborts on
conflicts, leaving the repository untouched.

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the whole plan. Done so far:

1. **Core** (done): agent plugins, worktrees, task store, terminal CLI,
   optional Markdown/Obsidian memory.
2. **Discord channel** (done): slash commands, notifications, diff/merge/discard buttons.
3. **Local voice** (done): `dia voice toggle` on a desktop shortcut →
   faster-whisper → brain → Piper, plus an optional wake word (openWakeWord).
4. **Brain + memory** (done): routing requests, multi-step plans, search
   across notes, and facts Dia proposes for project notes, kept only on
   approval.
5. **Cross-review and plans** (done): any agent reviews another's work, with
   fix rounds; multi-step plans across agents; usage-limit aware fallback
   between agents.
6. **Forges** (done: push + PR/MR, CI watching and fixing). Next: review
   comments from the PR/MR back into tasks (done), a project watcher that
   tests new commits and offers a fix (done). Next: Discord voice channel,
   more toolchains.
