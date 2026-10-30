# Desktop app, web UI and KDE widget

`dia serve` also serves a local web UI and API on <http://127.0.0.1:8765>:

- **Inbox** (the start view): what waits for your decision (changes to
  merge with their +/− lines, plans, failed CI, review comments) with its
  main action, what runs now, the current mission's steps and the agents
  (calls in the last 24 h, usage limits). The composer starts a task, a
  plan, a scenario, the AI council, or a research report.
- **Tasks**: give tasks (edit / read-only, review, plans, research), follow them live,
  see the diff and the test log, and Review / Merge / PR-MR / Discard /
  Fix CI / Address comments / Run plan.
- **Chat**: talk to Dia in your own words, as on Discord or by voice, in
  several conversations (sessions, each with its own history: docs/GOALS.md); plans
  wait for your yes. Every message shows its date and time (Chat, Talk, CLI
  sessions).
- **Status**: agents, projects (launch, test now, measure now, a command in
  a throwaway lab, impact, debt...), brain chain, memory, channels;
  **Skills** (weather, crypto, briefing... with their arguments) and
  **Tools**: Dia's commands with their output (doctor and `--fix`, sandbox
  check, usage limits, issues now, red-team test, or any of `bench`, `lab`,
  `why`, `impact`... typed in), so what has no button still works here.
  Research starts from the Inbox/Tasks composer, not here. **About** (O Dia)
  lists the author, solar9.me, GitHub, the license, and versions of Dia,
  Python, Qt, agent CLIs and other installed components. Jump chips pin the
  sections. The same page lives under Settings → About Dia.
- **Usage**: tiles, per-agent and per-day charts side by side when there is
  room, and scrollable tables on a narrow window.
- **Settings**: a side menu in four groups (You and Dia, Work, Connect,
  This computer). Notifications (push, quiet hours, budget) sit with You
  and Dia; Discord with Integrations; the local web UI and port with
  Desktop; remote URL and hosts with Devices; computer alerts, tidy, lab
  and Godot analysis under Desktop. Appearance is only themes; startup,
  services, shortcuts, the tray and the KDE widget live under Desktop &
  services; sandbox and host lists under Security. Everything else in the
  config has a place: assistant (including chat engines), voice and brains,
  agents (routing, review, missions…), projects, memory, automation,
  schedule, integrations, devices and remote access, secrets, and the
  config file itself (validated before it's saved), and About Dia (author,
  website, GitHub, license, component versions). Forms are one column;
  labels stack above fields on a phone.
- **Task detail**: a decision bar that stays in view (tests, review, +/−,
  Merge / PR-MR / Discard...), and tabs: Summary, Changes (a per-file diff with
  line numbers and collapsible sections; the decision bar expands downward to a
  short, scrollable file list; click a file to jump in the diff; PR/MR review
  comments stay under the lines they are about), Tests, Reviews.
- **Shortcuts**: Ctrl+K searches (views, tasks by text, id or branch,
  actions); Ctrl+B folds the sidebar down to its icons (remembered).
- **Voice**: the button in the sidebar works like the `dia voice toggle`
  shortcut and shows when Dia listens, thinks or speaks.

## Open it

```bash
pip install -e '.[qt]'      # aiohttp for the UI + PySide6 (Qt WebEngine) for the window
dia app                     # own window; starts `dia serve` in the background if needed
dia app --view chat         # ... on a given tab (inbox, tasks, missions, chat, memory, status, usage, settings)
dia ui --open               # or in your browser
```

On Arch the system packages work too: `sudo pacman -S pyside6 qt6-webengine`
(a virtualenv then needs `--system-site-packages`).

Dia's own window (Qt) has Dia's icon on the taskbar and **an icon in the
tray**: a left click opens or raises the window; its menu goes straight to a tab,
talks to Dia, toggles quiet mode, and controls Dia/Ollama services. Minimizing and the window's
X hide it to the tray; Settings → Desktop & services → Desktop window (or `[app]
minimize_to_tray`, `close_to_tray`, `tray`) changes that. “Close icon and window” leaves background services running; “Stop Dia and quit”
stops the service group and, in linked mode, Ollama. Stop/restart asks for
confirmation and shows the last observed active task IDs.

Updates: every few hours the app looks at Dia's GitHub releases. When a newer one exists
the tray menu gets “Update X available — install”; on your click the release wheel is checked
against its `SHA256SUMS`, installed into Dia's own environment and Dia restarts. A source
checkout (`pip install -e`) is never touched. An Arch/`pacman` install (files under `/usr`)
never runs `pip`: the tray says to update with the package manager
(`sudo pacman -Syu dia-assistant`). `[app] check_updates = false` disables the check.
Private builds from before the version reset (0.1.0–0.2.3) still see ≥0.1.1 as newer.
Running `dia app` again shows the window that is already open. While Dia
is stopped or starting the window shows a page with a Start button; without
the system frame that page is the title bar too (drag, double-click, edges,
minimize / maximize / close).

The window has **Dia's own title bar**, like Obsidian or Cursor: no system
frame; the sidebar's top and the top bar drag the window (a double click
maximizes it), the edges resize it, and minimize / maximize / close sit at
the top right in Dia's colours. `[app] custom_titlebar = false` (Settings →
Desktop & services) brings back the system's title bar after reopening the window.

Without Qt, `dia app` uses pywebview (`pip install -e '.[app]'`; no tray),
then a Chromium/Chrome/Brave app window (no tabs or address bar), or your
default browser.

## KDE Plasma widget

```bash
dia plasmoid install        # then: right-click the panel → Add or Manage Widgets → Dia
```

The widget wears Dia's theme (the one picked in Settings → Look). The panel shows Dia's icon: **grey** while she is not listening, **in the theme's accent**
while she listens and thinks, **pulsing** while she speaks; a badge counts
what waits for your decision. Middle click talks right away. Left click opens
the popup:

- **Talk to Dia** (the same as `dia voice toggle`), or **write** to her: the
  answer shows right there.
- **Waiting for you**: cards like the app's Inbox, with the +/− lines:
  "Review changes" opens the task in Dia's window, a plan runs with "Run plan".
- **Working now**: the tasks that run; a click opens one.
- Buttons for the Inbox, Tasks, Chat, Status and Settings, quiet mode and the
  emergency stop (two clicks); Resume after a stop.

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

Dia's icon takes the theme's `--accent`: in the sidebar, as the browser tab's
icon and, in Dia's own window, as the window's and the tray's icon (kept in
`app-accent` in Dia's data folder, so the next start and the "Dia is stopped"
page match it), and in the KDE widget.

**Themes everywhere** (Settings → Look): Dia keeps them (`ui-theme.json` in
her data folder, `/api/theme`), not the browser. The app's theme is used by
Dia's window and the browser; the phone and the KDE widget use it too, or each
its own ("Same as the app" / "Its own"). A paired phone picks only its own. Open
pages switch at once; the widget within a few seconds.

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

The phone apps (Android / iOS) pair with Dia over the network; see
[MOBILE.md](MOBILE.md).

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
Start/restart of the session target uses `systemctl --no-block`, so a slow model
warmup (often well over a minute) cannot trip the 90s control timeout and show a
false failure dialog while Dia is already running.

The native `dia app --background` login path creates only the existing tray icon.
If the tray is disabled/unavailable it starts services without opening a window.
Left click always shows/raises the window. A background launch never shows an
already running window. A managed backend that was stopped stays stopped when
opening the app; the window displays an offline page with a Start button.
Status polling and service control run outside the Qt event thread. The tray has
start/stop/restart and recent journal entries for Dia and Ollama.

Settings → Desktop & services → Startup and services uses the same runtime module. Actions that
stop/restart the HTTP backend run in a separate transient systemd unit so stopping
Dia cannot kill its own controller. The response says “scheduled”; subsequent
state polling reflects the result. Desktop service control is local-owner-only,
including for paired devices with full access. Systemd logs of the transient
`dia-control-*` units contain any execution errors.

The Plasma widget polls `dia runtime status` separately from the HTTP API. It
shows Dia/Ollama unit states even when the backend is stopped; polling never
starts services. Left click opens the widget's popup (its "Open Dia" button raises the desktop
window), middle click uses voice only while connected. Right click offers the app, settings,
and start/stop/restart for both services. The panel keeps the chat/task controls
and adds service rows. Stop/restart asks for confirmation. CLI errors are shown
in the panel and service state is refreshed every four seconds.

Lifecycle follow-up: legacy installations can stop before the new target exists;
native login creates the tray before starting services, so model warmup or an
authorization prompt cannot delay the icon. Non-native launches still wait for
the HTTP UI. Scheduled settings actions persist their queued/running/done/failed
result in `service-operation.json`, including errors, and Settings displays it.
(Desktop validation logs: [test-reports/2026-10-26-desktop-validation.md](test-reports/2026-10-26-desktop-validation.md).)

## CLI sessions

The **CLI sessions** tab lists every Claude Code, Codex and Cursor Agent running on
this computer, also those you started by hand in a terminal, and shows the
conversation of the one you pick (read from the files the CLIs keep in
`~/.claude`, `~/.codex` and `~/.cursor`; read-only, refreshed every few seconds).
Found by scanning the process table, so Linux only; owner-only: paired phones
do not get it. `GET /api/cli-sessions` and `/api/cli-sessions/{pid}/transcript`.

**New session** (button in the tab): pick an agent (Claude Code, Codex or Cursor
Agent), its model, a project, edit or read-only, and whether it may use the web;
Dia starts the agent headless in the project's folder with your first message
and keeps the conversation in the app like a taken-over one: answer it here,
**Release** shows the command to go on in a terminal. `POST /api/cli-captured`.

Taken-over sessions accept the same slash commands as that agent's own CLI
(`/help`, `/compact`, `/model`, `/permissions`, `/mode`…). Type `/` to pick
one. Dia handles help, status, model, mode/plan/permissions/approvals and
release itself; the rest is sent as you would type it in a terminal.
`GET /api/cli-commands`, `PATCH /api/cli-captured/{id}`.

**Take over** (button in the tab): ends the CLI process in its terminal (SIGTERM; its
conversation stays in the CLI's own file) and keeps the conversation in the app,
where you can read and answer it: each reply resumes it headless in its folder
(`claude --resume`, `codex exec resume`, `cursor-agent --resume`, as the agent's
own sandbox allows). **Release** hands it back; the tab shows the command to
resume it in a terminal again (`claude --resume <id>` and so on). Only one
side writes at a time: a live terminal session cannot be steered from outside, which
is why a session is taken over, not shared. The list of taken-over sessions is
`captured_sessions.json` in Dia's data folder.

## UI design concept (2026-10-28)

A standalone [interactive UI concept](design/ui-concept/index.html) explores
clearer task review, a calmer chat layout and grouped appearance/desktop settings.
See the [design notes and three rendered previews](design/ui-concept/README.md).
It uses fictional data and does not connect to the API or change the production UI.
