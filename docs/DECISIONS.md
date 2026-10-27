# A memory of decisions

Notes say what is true now. Decisions say why: what was tried, what was
turned down, what came back out. Dia keeps both and uses them.

## The decision log

Every one of these becomes a record (the `decisions` table in Dia's local
database), with the reason when you give one:

| Decision | How the reason gets there |
|---|---|
| a task merged | `dia merge ID --reason "..."`; the UI asks when you click Merge |
| a task discarded | `dia discard ID --reason "..."`; the UI asks |
| a merge rolled back | `dia rollback ID --reason "..."`; the UI asks |
| a plan rejected | discarding a plan, or saying "nie" when Dia proposes one |
| a review verdict | the reviewer's findings are kept as the reason |

The reason is optional, but it is what makes "why" answerable months later.

Asking:

```
dia why "dlaczego trzy miesiące temu zrezygnowaliśmy z ECS w ekwipunku?"
2026-07-21 discard: discarded  [nova] Rewrite the inventory as ECS (task 20260721-1012-ab12)
    why: ECS made the save format incompatible
commits:
    nova: 3f2a1c9 2026-07-20 Spike: inventory as ECS
```

or "Dia, dlaczego zrezygnowaliśmy z ECS?", or the Decisions card in the
Memory view (`/api/why?q=...`). Dia finds the decisions about the subject of
the question, adds what came of each one (tests, rolled back later, a
benchmark made worse, security incidents), and the notes and commits that
mention it. Name the thing (a feature, a library, a file): the search is by
words and forgiving about Polish endings, so it doesn't need the exact
phrasing. `dia decisions [-p nova]` lists the log.

## Your working-style profile

From the decision log, plus the commits you made yourself on files an agent
had just changed (what you fix after agents), an agent drafts a short
profile: what you accept, what you reject, what you correct, your
priorities. Only patterns with evidence, phrased as guidance for an agent.

```
dia profile --update      # draft (it waits for you)
dia profile               # the current profile
dia profile --accept      # make the draft the profile
```

or the "Your working style" card in the Memory view, where you can also
edit it directly. Updates keep what is in the current profile, including
your own edits. The profile is the note `Working style.md` in Dia's memory
folder (or `profile.md` in Dia's data directory without memory). Agents get
it with every task, and "jak ja bym to zaprojektował?" is answered from it,
next to an alternative.

```toml
[profile]
agent = "claude"      # who drafts it; model = "...", timeout = 300
```

## Notes that contradict the code

```
dia contradictions nova
1 note(s) contradict the code:
- Saves are JSON files → Saves are stored in SQLite (user://save.db). (save.gd:12 opens a SQLite database)
accept the corrections: dia learned 20261025-1100-cd34 --accept all
```

An agent, read-only, checks the concrete claims in the project's notes and
its docs (README, docs/, module headers) against the code. Each
contradiction comes back with evidence and a corrected sentence, as a
proposal like a fact learnt after a task: accept it (`dia learned`, the
Memory view) and it is added to the project note. Docs in the repository
are only reported, never edited. Also: the "Check notes against code"
button per project in Status, "Dia, sprawdź, czy notatki nova są aktualne",
or a schedule ("co tydzień sprawdzaj notatki nova").

## What could break?

```
dia impact nova dash
dash: fx/dash_fx.tscn, player/movement.gd
uses it (directly or through others):
  player/player.gd
  player/player.tscn  (via player/player.gd)
  levels/level1.tscn  (via player/player.tscn)
usually changes together with it:
  hud/hud.gd  (7 of 9 commits)
tests: test/test_movement.gd
```

The target is a path, a file name, or a word: it matches file names,
`func dash`/`class_name`, and node names in scenes. In a Godot project the
graph comes from `ext_resource` paths, `preload`/`load`, `extends`, a
`class_name` used by name and autoloads, followed back three steps; in any
project, files that mention the target's name. History adds files that
change in the same commits often enough to be a habit, and the tests are
those among them plus tests that name the target. `--agent` hands it to an
agent that reads the code and says what is likely to break and what to test
by hand. Also: "co się może zepsuć, jeśli zmienię dash?", the field per
project in Status, `/api/projects/nova/impact?q=dash`.
