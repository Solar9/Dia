# Desktop app, web UI and KDE widget

`dia serve` also serves a local web UI and API on <http://127.0.0.1:8765>:

- **Tasks**: give tasks (edit / read-only, review, plans), follow them live,
  see the diff and the test log, and Review / Merge / PR-MR / Discard /
  Fix CI / Address comments / Run plan.
- **Chat**: talk to Dia in your own words, as on Discord or by voice, in
  several conversations (sessions, each with its own history: docs/GOALS.md); plans
  wait for your yes.
- **Status**: agents, projects (launch, test now, measure now, a command in
  a throwaway lab, impact, debt...), brain chain, memory, channels;
  **Skills** (weather, crypto, briefing... with their arguments) and
  **Tools**: Dia's commands with their output (doctor and `--fix`, sandbox
  check, usage limits, issues now, red-team test, or any of `bench`, `lab`,
  `why`, `impact`... typed in), so what has no button still works here.
- **Settings**: everything in the config file has a place: assistant,
  voice and brains (with a brain test and replay), agents (and adding your
  own), projects (adding and editing), memory, automation, integrations,
  schedule, secrets, devices and remote access, look, the desktop window
  and tray, shortcuts / start at login / the service / the KDE widget, and
  the config file itself (validated before it's saved).
- **Voice**: the button in the sidebar works like the `dia voice toggle`
  shortcut and shows when Dia listens, thinks or speaks.

## Open it

```bash
pip install -e '.[qt]'      # aiohttp for the UI + PySide6 (Qt WebEngine) for the window
dia app                     # own window; starts `dia serve` in the background if needed
dia app --view chat         # ... on a given tab (tasks, missions, chat, memory, status, usage, settings)
dia ui --open               # or in your browser
```

On Arch the system packages work too: `sudo pacman -S pyside6 qt6-webengine`
(a virtualenv then needs `--system-site-packages`).

Dia's own window (Qt) has Dia's icon on the taskbar and **an icon in the
tray**: a left click opens or raises the window; its menu goes straight to a tab,
talks to Dia, toggles quiet mode, and controls Dia/Ollama services. Minimizing and the window's
X hide it to the tray; Settings → Look → Desktop window (or `[app]
minimize_to_tray`, `close_to_tray`, `tray`) changes that. “Close icon and window” leaves background services running; “Stop Dia and quit”
stops the service group and, in linked mode, Ollama. Stop/restart asks for
confirmation and shows the last observed active task IDs.

Updates: every few hours the app looks at Dia's GitHub releases. When a newer one exists
the tray menu gets “Update X available — install”; on your click the release wheel is checked
against its `SHA256SUMS`, installed into Dia's own environment and Dia restarts. A source
checkout (`pip install -e`) is never touched; `[app] check_updates = false` disables the check.
Running `dia app` again shows the window that is already open.

The window has **Dia's own title bar**, like Obsidian or Cursor: no system
frame; the sidebar's top and the top bar drag the window (a double click
maximizes it), the edges resize it, and minimize / maximize / close sit at
the top right in Dia's colours. `[app] custom_titlebar = false` (Settings →
Look) brings back the system's title bar after reopening the window.

Without Qt, `dia app` uses pywebview (`pip install -e '.[app]'`; no tray),
then a Chromium/Chrome/Brave app window (no tabs or address bar), or your
default browser.

## KDE Plasma widget

```bash
dia plasmoid install        # then: right-click the panel → Add or Manage Widgets → Dia
```

The panel shows Dia's icon: **grey** while she is not listening, **purple**
while she listens and thinks, **pulsing** while she speaks; a badge counts
what waits for your decision. Middle click talks right away. Left click opens
the popup:

- **Talk to Dia** (the same as `dia voice toggle`), or **write** to her: the
  answer shows right there.
- **Waiting for you**: finished tasks to merge or discard and plans to
  approve; a click opens the task in Dia's window.
- The latest tasks, and buttons for Dia's window, Chat, Status, Settings,
  quiet mode and the emergency stop (two clicks); Resume after a stop.

The widget calls this installation of Dia (its path is filled in at install
time) and needs `dia serve` running, e.g. as a service (`dia service install`).

## Themes

A theme is a CSS file that sets colour, font and radius variables. Copy a
built-in one and change it:

```bash
mkdir -p ~/.config/dia/themes
cp "$(python -c 'import dia, pathlib; print(pathlib.Path(dia.__file__).parent)')/ui/static/themes/dark.css" \
   ~/.config/dia/themes/mine.css
```

It appears under **Settings → Your themes**. Built-in: `dark`, `light`,
`midnight`. Every theme must define the same variables as `dark.css`.

Code in diffs and in agents' messages is highlighted with Prism (GDScript,
Python, C#, JS/TS, Rust, C/C++, Go, Java, TOML, JSON, YAML, Markdown, shell,
Godot scene/resource files...). Its colours are the theme's `--syntax-*`
variables.

## Security

- The server listens on `127.0.0.1` only. Requests addressed to any other host
  name are refused, which also blocks DNS-rebinding attacks from web pages.
- Every API call needs the token in `<data_dir>/api-token` (file mode 600,
  created on first start). `dia ui` / `dia app` pass it to the page in the URL
  fragment, which is never sent over the network; the page keeps it in local
  storage. `dia ui --token` prints it.
- Configure with `[ui] port = 8765` or turn it off with `[ui] enabled = false`.

A phone app over the network will come later, with its own authentication.

## Shared desktop lifecycle

`dia runtime status` reports JSON directly from systemd without needing the HTTP
server. `dia runtime start|stop|restart [dia|ollama]` controls the named services.
`dia runtime configure --autostart --ollama with-dia --warmup` applies the login
policy; use `--no-autostart`, `--no-warmup`, or Ollama `independent` / `manual`
for the other modes. Settings are stored in the user's `dia/startup.json`.

The login entry starts the desktop launcher. A user `dia-session.target` groups
`dia.service` and the existing optional `dia-local-brain-warmup.service`.
Applying a policy removes the old individual enable links, including warmup
(which could otherwise start Dia indirectly). Changing login settings does not
stop running services. Existing Ollama user/system services and models are kept;
system service changes may require authorization through the desktop's polkit
agent. Errors are reported, and a failed operation does not save the new policy.
The status includes actual unit states so partial changes remain visible.

Phase 1 validation: 14 focused lifecycle, shortcut and service tests pass with
isolated configuration and a simulated systemctl; no host services were changed.

The native `dia app --background` login path creates only the existing tray icon.
If the tray is disabled/unavailable it starts services without opening a window.
Left click always shows/raises the window. A background launch never shows an
already running window. A managed backend that was stopped stays stopped when
opening the app; the window displays an offline page with a Start button.
Status polling and service control run outside the Qt event thread. The tray has
start/stop/restart and recent journal entries for Dia and Ollama.

Settings → Look → Startup and services uses the same runtime module. Actions that
stop/restart the HTTP backend run in a separate transient systemd unit so stopping
Dia cannot kill its own controller. The response says “scheduled”; subsequent
state polling reflects the result. Desktop service control is local-owner-only,
including for paired devices with full access. Systemd logs of the transient
`dia-control-*` units contain any execution errors.

Phase 2 validation: 37 focused Qt/runtime/API tests pass, including a fresh
process checking hidden login, duplicate background launch and repeated left
clicks. Ruff and JavaScript syntax checks pass. Tests do not change host services.

The Plasma widget polls `dia runtime status` separately from the HTTP API. It
shows Dia/Ollama unit states even when the backend is stopped; polling never
starts services. Left click opens the widget's popup (its "Open Dia" button raises the desktop
window), middle click uses voice only while connected. Right click offers the app, settings,
and start/stop/restart for both services. The panel keeps the chat/task controls
and adds service rows. Stop/restart asks for confirmation. CLI errors are shown
in the panel and service state is refreshed every four seconds.

Phase 3 validation: all 364 tests pass; `qmllint` reports no diagnostics.
`plasmawindowed --smoke-test` loads a temporary copy with an inert CLI command
and exits successfully under an isolated D-Bus session/offscreen platform. The
session emits portal/accessibility warnings, but no widget QML errors. This is
not a manual interaction test of the installed panel widget.

Lifecycle follow-up: legacy installations can stop before the new target exists;
native login creates the tray before starting services, so model warmup or an
authorization prompt cannot delay the icon. Non-native launches still wait for
the HTTP UI. Scheduled settings actions persist their queued/running/done/failed
result in `service-operation.json`, including errors, and Settings displays it.

Validation: 43 focused tests passed after the follow-up, followed by all 11
runtime tests including the operation report. A real user-systemd integration
check with disposable, uniquely named sleep/oneshot services verified group
start, PID-changing restart, and stop of both members and target. All disposable
units and drop-ins were removed afterwards; the real Dia/Ollama services were
not involved in that test.

Local rollout (2026-10-26): updated the installed Plasma widget package and
restarted `dia.service` after confirming no active tasks and idle voice. The new
`/api/desktop` response includes runtime status; both Dia and Ollama are active.
Autostart policy and Ollama enablement were not changed. Existing native windows
need to be closed from the tray and reopened to load the new tray code; an
already loaded Plasma widget needs a shell reload or a new login.

## CLI sessions

The **CLI sessions** tab lists every Claude Code, Codex and Cursor Agent running on
this computer, also those you started by hand in a terminal, and shows the
conversation of the one you pick (read from the files the CLIs keep in
`~/.claude`, `~/.codex` and `~/.cursor`; read-only, refreshed every few seconds).
Found by scanning the process table, so Linux only; owner-only: paired phones
do not get it. `GET /api/cli-sessions` and `/api/cli-sessions/{pid}/transcript`.

**Take over** (button in the tab): ends the CLI process in its terminal (SIGTERM; its
conversation stays in the CLI's own file) and keeps the conversation in the app,
where you can read and answer it: each reply resumes it headless in its folder
(`claude --resume`, `codex exec resume`, `cursor-agent --resume`, as the agent's
own sandbox allows). **Release** hands it back; the tab shows the command to
resume it in a terminal again (`claude --resume <id>` and so on). Only one
side writes at a time: a live terminal session cannot be steered from outside, which
is why a session is taken over, not shared. The list of taken-over sessions is
`captured_sessions.json` in Dia's data folder.
