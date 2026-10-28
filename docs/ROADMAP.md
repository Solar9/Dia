# Roadmap

Dia aims to be a personal operating system on top of AI: one assistant that
runs coding agents, knows your projects, looks after your computer and day,
and asks before anything irreversible.

- **0.1.0** (first public release, 2026-10-27): everything on this page, the
  capability map and milestones 1 to 5 below; see [CHANGELOG.md](../CHANGELOG.md).
  Dia moves from an assistant that does what it is asked to one that can be
  trusted with more, because it is **contained**, it **measures** what it does
  and it **remembers why**.
- **0.1.1** (2026-10-28): UI 2.0 and release hygiene; see [PLAN-0.1.1.md](PLAN-0.1.1.md)
  and [CHANGELOG.md](../CHANGELOG.md).
- **Next**: not planned yet; remaining items in PLAN-0.1.1 (DIA-01 smoke, nice leftovers).

## Milestones

Guiding rules: Dia proposes and you approve anything
irreversible; more autonomy only comes with stronger containment; numbers
from tests and benchmarks beat a model's confidence; nothing watches you in
the background without an explicit, visible opt-in.

### Milestone 1: containment ✅ done (first, because everything after it gives agents more room)

| Feature | What it means |
|---|---|
| ✅ **Agent sandbox** | Agents (and project tests) run in bubblewrap: their worktree, login and tools only; not `~/.ssh`, `~/.config/dia`, other projects or Dia's data; git data read-only except their task branch; Dia's secrets out of their environment. Per agent and project allow-lists; on where bubblewrap works. (Landlock as a second layer: later.) |
| ✅ **Behaviour guard** | Decoy secrets in the sandbox; an agent that reads one is stopped, its work not kept, the incident recorded on the task, in the audit log and as an urgent alert. Reaching for secret paths is a lesser incident. (Watching network use: later.) |
| ✅ **Red-team suite** | A hostile repository (injection in README, code, TODO, notes) and a scripted agent that obeys it, in the test suite and CI; `dia redteam` runs the real agents against it and reports resisted / contained / BREACH. (Injection through issues, web pages and review comments: more fixtures later.) |
| ✅ **Disposable lab** | `dia lab`: a command in a throwaway Podman/Docker container on a copy of a project, without network or privileges by default. |

### Milestone 2: experiments and measurement ✅ done

| Feature | What it means |
|---|---|
| ✅ **Experiments** ("co by było, gdyby…", R&D lab) | A question becomes N variants on their own branches (one per agent, or per approach), each tested and run against the same benchmark; Dia shows a table (tests, size of change, every metric against the base branch) and a recommendation. Nothing is merged. `dia experiment`, the assistant, the Status view. |
| ✅ **Benchmarks per project** | `[projects.X] benchmark`: a command that prints metrics (a Godot benchmark scene, build time, test time), run sandboxed on a clean copy, the median of several runs. Results are kept over time; a regression after a merge is reported with the commits that came in and counts against the agent. (Proposing a fix as a task: later.) |
| ✅ **Dia scorecard** | How well Dia itself works, week over week: tasks done, discards, rollbacks, retry rescues, review rounds, minutes per task, sandbox incidents, benchmark regressions. `dia scorecard`, the Usage view. (Planning accuracy and memory hits: later.) |
| ✅ **Agent evolution** | Quality, not only success: rollbacks, benchmark regressions and extra review rounds lower an agent's score; proposals ("careful: 83 %; hasty: 100 % done (1 rolled back, 1 made it slower)") and automatic routing use it. Proposals stay proposals. (Per kind of task: later.) |
| ✅ **Shadow brain** | Requests are logged; `dia brains --replay 50 --brain local` gives them to another brain without executing anything and shows how often it agrees, and where not. |

### Milestone 3: a memory of decisions ✅ done

| Feature | What it means |
|---|---|
| ✅ **Decision log** | Every merge, discard, rollback, rejected plan and review verdict, with the reason when you give one (`--reason`, the UI asks), becomes a decision record. `dia why "dlaczego zrezygnowaliśmy z ECS?"` (or ask Dia) finds the decisions, what came of them (rolled back, benchmark regressions, tests, incidents), and notes and commits that mention it. |
| ✅ **Working-style profile** (the "digital twin", lightly) | From the decision log and your own commits on files an agent had just changed ("what you fix after agents"), an agent drafts a short profile: patterns you accept and reject, what you correct, your priorities. It waits for your approval, is a note you can edit, and agents get it with every task; "jak ja bym to zaprojektował?" is answered from it, with an alternative. |
| ✅ **Contradiction check** | `dia contradictions nova` (or "sprawdź, czy notatki nova są aktualne", or a schedule): an agent, read-only, checks the claims in the project's notes and docs against the code; contradictions come back with evidence and a corrected sentence, as proposals like learnt facts. Docs in the repository are only reported. |
| ✅ **Impact analysis** (the knowledge graph, practically) | `dia impact nova dash`: in a Godot project, which scenes, scripts and resources use the target (ext_resource, preload/load, class_name, autoloads), followed back three steps; in any project, files that name it; files that change together with it in git history; the tests that cover it. `--agent` adds an agent's reading of what is likely to break. |

### Milestone 4: quality guards ✅ done

| Feature | What it means |
|---|---|
| ✅ **Architecture guardian** | Rules per project: prose in `ARCHITECTURE.md` (the reviewer checks each change against it and reports `VIOLATION:` lines) and forbidden dependencies (`architecture_forbid`, checked statically on every change from the `dia impact` graph). A violation blocks merging until you override it with a reason, which goes into the decision log. |
| ✅ **Technical debt register** | `dia debt nova`: long functions, deep nesting, large files, duplicated code, hot code without tests, vulnerable dependencies (`--deps`), ranked by benefit (how often the file changes) × severity ÷ cost. Paying an item off is an ordinary task (`--fix N`, the UI). (Outdated, not vulnerable, dependencies: later.) |
| ✅ **Debugging swarm** | `dia debug nova "..."`: agents with roles (logs, code, history) propose causes in parallel; the most backed ones each get a test that fails if the cause is real. Tests decide, not votes; a confirmed cause is fixed from its test's branch. |
| ✅ **Verification gate** (metacognition, measurably) | After a large change (150+ lines, or `always`), the author states its assumptions and a command to check each; Dia runs them in the sandbox. What is recorded is how many held, not how sure the agent felt; a failed one blocks merging like a violation. |

### Milestone 5: goals and context ✅ done

| Feature | What it means |
|---|---|
| ✅ **Goals** | `dia goal new uv "Starfall do Early Access" --weeks 8`: milestones from a planner; a weekly review (in `dia serve`, or on request) of the missions and tasks for it, blockers (failures, rollbacks, regressions, incidents) and recent commits; the next mission proposed, prepared only when you approve. |
| ✅ **Plan simulation** | Every plan and mission shows the files it will likely touch (named, found, or changed by similar tasks), the expected agent minutes and calls from history, risks (earlier rollbacks or regressions there, debt, architecture rules, no tests, a large change) and the points that wait for you. Nothing runs before you accept. |
| ✅ **Work profiles** | `[profiles.starfall]` with a project and apps: "zaczynam pracę nad Starfall" opens them and tells you where you left off (last tasks, waiting reviews, the goal, your note); "kończę na dziś" saves the session. Only your configured commands start; nothing about what you do in them is recorded. |
| ✅ **One conversation across devices** | The owner's identities (desktop UI, paired devices, voice, `[assistant] owner_ids` such as your Discord id) share one conversation: its recent turns and the plan waiting for a "yes", across channels and restarts. |
| ✅ **Discreet suggestions** | From task, decision and git history only: trouble in one folder this week, tests that keep failing, hot debt, work waiting for review or approval. At most one a day by default, never repeated within two weeks, through quiet hours and the notification budget; accepting runs a read-only analysis or a debt task. |
| ✅ **Self-check** | Channels and watchers in `dia serve` run supervised and restart with back-off (`/api/health`, the Status view); tasks interrupted by a restart are recorded. `dia doctor --fix` removes leftover worktrees, rebuilds a broken memory index, restores private permissions and reports what it cannot fix. |

### Later, or not planned

- **Synthetic players** need a way to drive the game from tests; scripted
  playthroughs in GUT come first.
- **Tools written by Dia for itself** go through the normal path only: a task
  on Dia's repository, your review, your merge. Never self-registered.
- **Agent teams with their own leaders and budgets**: missions already split
  work with a budget; another layer would multiply agent calls on three
  usage-limited subscriptions for little gain. Reconsider when the scorecard
  shows missions are the bottleneck.
- **Spatial awareness from cameras** ("gdzie są moje słuchawki?"): not
  planned; it needs always-on cameras and affects everyone in the room.

## Capability map

### 1. Intelligence and personality

| Capability | Status | Notes |
|---|---|---|
| Natural conversation (text, voice) | ✅ | Discord, voice, UI chat, `dia say` |
| Long-term memory | ✅ | Markdown/Obsidian notes, journal, learned facts, semantic search |
| Planning | ✅ | multi-step plans across agents, pipelines |
| Model choice | ✅ | brain chain (rules → local → subscription); per-task agent choice by rules and record |
| Personality | ✅ | presets or your own description, your name |
| Proactivity | ✅ | schedule, briefing, watchers, quiet hours and a notification budget |
| Self-check | ✅ | tests, cross-review with fix rounds |
| Learning preferences | ✅ | project facts and personal preferences, both on your approval |
| Conversation context | ✅ | recent turns per conversation |

### 2. Agent orchestration

| Capability | Status | Notes |
|---|---|---|
| Delegation, parallel tasks, queue | ✅ | worktree per task, `max_parallel_tasks` |
| Review between agents | ✅ | |
| Monitoring | ✅ | UI live view, Discord, push |
| Failure recovery | ✅ | usage-limit fallback and waiting; retry policies (another attempt, another agent, fixing failed tests) |
| Cost/usage tracking | ✅ | Usage view |
| Agents passing work on | ✅ | plan steps see earlier steps |
| Dependencies between steps, parallel steps | ✅ | missions: a graph of steps on their own branches |
| Benchmarking agents | ✅ per project, with proposals you apply |

### 3. Computer control

| Capability | Status |
|---|---|
| Launch projects | ✅ (`dia launch`) |
| Resource monitor (CPU, RAM, disk, temperature) with alerts | ✅ |
| Processes and services (systemd, Docker) with approval | ✅ your own processes and user services |
| Updates check (pacman, flatpak) | ✅ reports only |
| Files (e.g. tidy Downloads) with a preview and approval | ✅ moves only, with undo |
| Clipboard | ✅ on request |
| Screen awareness: opt-in, visible indicator, one switch off | ✅ |

### 4. Game development

| Capability | Status |
|---|---|
| Godot: detect, context for agents, headless tests, launch | ✅ |
| Test scenarios ("does parry work?") as reports | ✅ an agent writes the test, Dia runs it and answers |
| Builds and exports, changelog from commits; publishing only on approval | ✅ builds and changelogs; publishing with the itch.io integration |
| Scene/resource analysis, performance hints | ✅ static analysis, optional agent advice |
| Balance analysis from gameplay data | ✅ from playtest telemetry, optional agent proposals |

### 5. Security (own systems only)

All active checks run only against hosts listed in the config as yours.

| Capability | Status |
|---|---|
| Dependency audit (pip-audit, npm audit, cargo audit) per project | ✅ osv-scanner first |
| Open ports and services on your machines | ✅ listening ports, scans of your hosts, new-port alerts |
| Network discovery of your own network | ✅ passive (ARP) and active (nmap -sn / ping) on networks you list; new devices reported |
| Log analysis (failed logins, unusual services) | ✅ failed logins, errors |
| Reports with proposed fixes as tasks | ✅ dependency fixes as tasks |

### 6. Voice

| Capability | Status |
|---|---|
| Wake word, push-to-talk, STT, TTS, Polish and English | ✅ |
| ElevenLabs voices (with fallback) | ✅ |
| Custom "Hej Dia" wake word | ✅ whisper-keyword (no training), or a trained openWakeWord model |
| Streaming answers, interrupting Dia | ✅ sentence by sentence; the shortcut interrupts |
| Quiet mode (text only while working or gaming) | ✅ |
| Speaker recognition | ✅ sherpa-onnx; unknown voices may ask for little |

### 7. Memory

| Kind | Status |
|---|---|
| Episodic (task history, journal) | ✅ |
| Project memory (notes, learned facts) | ✅ |
| Semantic search | ✅ |
| Browse, correct and delete memories in the UI | ✅ |
| Procedural memory (how-tos the agents follow) | ✅ written from a finished task, kept on your yes |

### 8. Internet and integrations

| Integration | Status |
|---|---|
| GitHub, GitLab (PR/MR, CI, reviews, issues) | ✅ |
| Discord | ✅ |
| Obsidian | ✅ |
| Weather, news, markets | ✅ |
| Web research reports (autonomous research) | ✅ with sources, kept as notes |
| Google Calendar, Gmail | ✅ read-only (iCal, IMAP) |
| Home Assistant | ✅ |
| itch.io (butler), Steam | ✅ on your approval; Steam never live on the default branch |
| Notion | ✅ search, read, add notes |

### 9. Automation

| Capability | Status |
|---|---|
| Daily briefing, schedule (cron, by voice) | ✅ |
| Broken builds, new commits, CI, review comments | ✅ |
| System events (CPU temperature, server down, new dependency versions) | ✅ temperature, disks, memory, battery, URLs; dependency versions with the audits |
| Notification budget / quiet hours | ✅ held notifications come as a summary |

### 10. Smart home

Work modes ("tryb pracy": lights, apps, notifications) through Home
Assistant. ✅ scenes and devices by name, schedulable; sensitive devices on a yes.

### 11. Interfaces

| Interface | Status |
|---|---|
| Desktop app, KDE widget, web UI | ✅ |
| Phone app (PWA), push notifications | ✅ |
| Short replies on the phone, detail on the desktop | ✅ |
| Mission Control: everything every agent is doing, live | ✅ Missions view, activity feed |

### 12. Safety and control

| Capability | Status |
|---|---|
| Permission levels; merging, pushing, publishing only on approval | ✅ |
| Isolation (worktrees) | ✅ |
| Secrets file (mode 600), device tokens, owner-only settings | ✅ |
| Limits on parallel work; usage limits | ✅ |
| Audit log of every action | ✅ with the actor (device, Discord user, voice, schedule) |
| Emergency stop (stop all agents now) | ✅ everywhere, phone included |
| Time and resource limits per task | ✅ agent minutes and calls, call timeout, CPU priority |
| Rollback (revert a merged task) | ✅ as a tested task you merge |

### 13. Beyond

| Idea | Status |
|---|---|
| Missions: a goal with budget, priority, agents, history; Dia plans, delegates, tests and reports, then waits for your decision | ✅ builds and changelogs come with the Godot work |
| AI Council: several models argue, Dia summarises a recommendation | ✅ |
| Self-improvement proposals ("Codex does this project's tests better") | ✅ default-agent proposals; never its own safety rules |
| Computer vision (screenshots; camera opt-in) | ✅ screenshots and single camera photos, both opt-in |
| Multi-device awareness | ✅ replies fit the phone, voice, Discord or desktop |

### In one paragraph

Core, agents, worktrees, approvals, Discord, voice, memory, review, plans,
forges, CI, Godot, UI, phone, usage limits, learning, watchers, persona,
skills, schedule, push, issues, semantic memory, usage, missions with step
graphs and budgets, Mission Control, emergency stop, audit log, conversation
context, quiet mode, memory browser, computer monitor and alerts, processes,
services, updates, screen awareness, Godot builds, changelogs and test
reports, security checks, calendar, mail, Home Assistant, itch.io, "Hej Dia",
speaking sentence by sentence with interruptions, AI Council, agent
benchmarking, device-aware replies, speaker recognition, active network
discovery, Steam, Notion, camera (opt-in), test scenarios, personal
preferences, retry policies, how-tos, quiet hours and a notification budget,
rollback, tidying Downloads, clipboard, Godot scene analysis, research
reports, balance from playtests, agent routing, limits per task.
