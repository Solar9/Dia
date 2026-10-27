# Your computer and your games

## How the computer is doing

"Dia, jak tam komputer?" / "co zjada procesor?", `dia say "..."`, or the
Status view (live meters for CPU, temperature, memory, disks and battery,
and the busiest processes). Read from `/proc` and `/sys`, no extra packages.

While `dia serve` runs, it raises an alert (Discord, voice, push, the app)
once per cooldown when something crosses a limit:

```toml
[system]
cpu_temp = 90            # °C
disk_used = 90           # % of any real filesystem
memory_used = 95         # %
battery_low = 15         # % while on battery
check_urls = ["https://my-server.example"]   # tells you when one stops answering
# watch = false          # no alerts
```

## Programs, services, updates

- "zamknij godota": Dia lists the matching programs of **your** user and asks
  before ending them; it never touches other users' processes, PID 1 or
  itself. Every ended process is in the audit log.
- "czy usługi działają?": failed systemd units (system and user) and
  Docker/Podman containers that are down. Dia can restart one of **your
  user's** services after a yes; system services need you (`sudo`), and Dia
  never uses sudo.
- "są aktualizacje?": pending updates from pacman (`checkupdates`, from
  pacman-contrib), paru/yay and flatpak (apt/dnf elsewhere), with the command
  to install them. Dia reports, never installs. Schedule it:
  `dia schedule add "0 9 * * 1" "aktualizacje"`.

## Seeing the screen (opt-in)

Off until you switch it on: the 👁 switch in the app's sidebar, "możesz
patrzeć na ekran", or `dia screen on`. A paired phone can switch it off, but
not on. While on, "co jest na ekranie?" or "dlaczego ten kod nie działa?"
takes a screenshot (spectacle on KDE, grim, gnome-screenshot, scrot or
ImageMagick), shows a notification and a pulsing indicator, gives the image
read-only to one agent (Claude Code reads images), and deletes it right
after. "nie patrz na ekran" or one click switches it off again.

```toml
[screen]
agent = "claude"     # default: the default agent
# keep = false       # true keeps screenshots in <data_dir>/screen (mode 700)
# command = ["spectacle", "-b", "-n", "-f", "-o", "{output}"]
```

## The camera (opt-in)

Off until you switch it on: the 📷 switch in the sidebar, "włącz kamerę", or
`POST /api/camera`; a phone can switch it off, not on. While on, "co widzisz
w kamerze?" takes **one** photo (ffmpeg from `/dev/video0`), shows a
notification, hands it read-only to an agent that reads images, and deletes
it. Nothing records or watches in the background; every photo is in the
audit log. "wyłącz kamerę" switches it off.

```toml
[camera]
device = "/dev/video0"
# agent = "claude"
# keep = false
# command = ["ffmpeg", "-f", "v4l2", "-i", "{device}", "-frames:v", "1", "{output}"]
```

## Godot: builds, changelogs, test reports

- Tests (every task, `dia check`, the watcher) now report GUT/gdUnit4 counts
  and the names of failing tests.
- `dia build nova` (or "przygotuj nową wersję testową nova", or Build on the
  project card in Status) tests a commit (default: the base branch) in a
  separate worktree, then exports every export preset into
  `~/.local/share/dia/builds/nova/<version>/<preset>/` with a CHANGELOG.md.
  It needs Godot's export templates (Editor → Manage Export Templates).
  Publishing (itch.io, Steam) stays yours.
- `dia changelog nova` lists the commits since the previous tag; `--write`
  lets an agent turn them into notes for players and testers.

```toml
[builds]
test_first = true
# presets = ["Linux", "Windows Desktop"]   # default: all export presets
# changelog_agent = "claude"
# changelog_model = "haiku"
```

### Does it work? Test scenarios

"Dia, czy parry działa w nova?" (or `dia scenario nova "parry in the last
0.2 s before a hit"`, `POST /api/scenarios`) has an agent write a test for
exactly that, in GUT or gdUnit4 when the project has one, without touching
the game code. Dia runs the project's tests and answers: it works, it
doesn't (with the failing output and the agent's description of the bug),
or it couldn't be tested. The test stays on the task's branch: merge it to
keep it as a regression test. A failing scenario is the answer, so retry
policies never "fix" it.

### Steam

```toml
[builds.steam]
app_id = 1234560
depots = { "Linux" = 1234561, "Windows Desktop" = 1234562 }
username = "your_build_account"   # log in once yourself: steamcmd +login <name>
branch = "beta"                   # set the build live there (optional)
```

**Publish on Steam** on a finished build, or `dia publish-build <task>
--steam`, uploads it with `steamcmd`. Dia never sets a build live on the
default branch: that stays your click in Steamworks.

## Tidying Downloads

"Dia, posprzątaj pobrane" (or `dia tidy`, Status → Tidy Downloads) shows what
would move where: images to Obrazy/, documents, archives, installers, video,
audio..., and files untouched for 30 days to Archiwum/<month>/. Nothing moves
until you say yes. Then Dia moves (never deletes, never overwrites: a taken
name gets a number) and keeps a record; "cofnij porządki" (`dia tidy --undo`)
puts everything back. Folders, hidden files and unfinished downloads stay.

```toml
[tidy]
folders = ["~/Pobrane"]   # the only folders Dia may tidy (default: Downloads)
archive_days = 30         # 0: no archive
# groups = { "Obrazy" = ["jpg", "png"], "Książki" = ["epub", "pdf"] }
```

## Godot: scene and performance analysis

`dia analyze nova` (Status → Analyse, or "przeanalizuj sceny nova") reads the
project's scenes, scripts and textures, no editor needed, and lists likely
problems: scenes with very many nodes or deep nesting, many real-time lights
or particle systems in one scene, node lookups (`$Node`, `get_node`) inside
`_process`, empty `_process` functions, huge textures. `--agent` (or "...i
doradź") lets an agent read the code and say which three matter most and how
to fix them. Limits: `[godot_analysis] max_nodes`, `max_depth`,
`max_lights`, `max_texture`.

## Godot: balance from playtests

Let the game log what happens while people play, one JSON object per line.
A minimal autoload (`Project → Autoload`, name `Telemetry`):

```gdscript
extends Node

var _file: FileAccess

func _ready() -> void:
    DirAccess.make_dir_recursive_absolute("user://telemetry")
    var name := Time.get_datetime_string_from_system().replace(":", "-")
    _file = FileAccess.open("user://telemetry/%s.jsonl" % name, FileAccess.WRITE)

func log_event(event: String, data: Dictionary = {}) -> void:
    data["event"] = event
    data["t"] = Time.get_ticks_msec() / 1000.0
    _file.store_line(JSON.stringify(data))
    _file.flush()
```

and call it where it matters: `Telemetry.log_event("level_end", {"level":
"1-2", "result": "win", "seconds": 184})`, `Telemetry.log_event("death",
{"level": "1-2", "cause": "bat"})`, `Telemetry.log_event("damage", {"weapon":
"sword", "amount": 12})`. Testers send you their `user://telemetry` folder (or
it is yours when you play). Then:

```toml
[projects.nova]
balance = { data = "~/.local/share/godot/app_userdata/Nova/telemetry" }
# min_attempts = 5, hard = 0.3, easy = 0.95, dominant = 0.6
```

`dia balance nova` (Status → Balance, "jak wygląda balans nova?") lists per
level the attempts, win rate, median time and deaths, what kills players and
which weapons do the damage, and flags what looks off. `--agent` lets an
agent read the game's code and propose concrete value changes.
