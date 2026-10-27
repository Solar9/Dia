# Discord setup

Dia's Discord bot lets you give tasks, get notified when they finish and
approve or reject the changes with buttons, from your phone or desktop.
The bot runs on your machine (`dia serve`); Discord is only the interface.

## 1. Create the bot (once)

1. Open <https://discord.com/developers/applications> → **New Application**
   (name it e.g. "Dia").
2. **Bot** tab → **Reset Token** → copy the token. Treat it like a password.
   No privileged intents are needed.
3. **OAuth2 → URL Generator**: scopes `bot` and `applications.commands`;
   bot permissions `Send Messages`, `Embed Links`, `Attach Files`,
   `Read Message History`. Open the generated URL and add the bot to your
   (private) server.
4. In Discord: **Settings → Advanced → Developer Mode** on. Then right-click
   your name → **Copy User ID**, and right-click the server → **Copy Server ID**.

## 2. Configure Dia

```toml
[channels.discord]
type = "discord"
allowed_users = [123456789012345678]   # your user id; nobody else can use the bot
guild_id = 987654321098765432          # your server: commands show up instantly
# token_env = "DIA_DISCORD_TOKEN"      # where the token is read from (default)
```

Keep the token out of the config file:

```bash
export DIA_DISCORD_TOKEN="paste-the-token"
pip install -e '.[discord]'
dia doctor        # "channel discord  ok"
dia serve
```

To keep it running in the background: `dia service install` (see below).

## 3. Use it

| Command | What it does |
|---------|--------------|
| `/run project prompt [agent] [read_only] [review]` | give a task; the agent works on its own branch |
| `/ask project question [agent]` | read-only question about a project |
| `/plan project goal [pipeline]` | propose a multi-agent plan; **Run plan** starts it |
| `/tasks [project]` | recent tasks |
| `/task task_id` | one task, with its review buttons |
| `/search query` | memory notes an agent would get |
| `/status` | agents, projects, memory, active tasks |

You can also just write to the bot in a direct message, or @mention it on
your server: "@Dia what does the inventory in nova do?". Dia's brain decides
what to do (see `[dia] brain` in the config); no extra Discord permissions are
needed for this.

When an edit task finishes, the bot replies and pings you with the summary,
changed files and test result, plus buttons:

- **Diff**: the full change (only you see it),
- **Review**: another agent reviews it and the author fixes what it finds,
- **PR / MR**: pushes the branch and opens a pull/merge request (see `forge`
  in the config),
- **Merge**: merges the task branch into the base branch of your checkout
  (refused if your checkout is on another branch; a conflicting merge is
  aborted and nothing changes),
- **Discard**: deletes the task branch.

The buttons keep working after `dia serve` restarts.

After **PR / MR**, Dia watches the pipeline and messages you when it finishes
(a DM, or `notify_channel_id`). A failed run comes with a **Fix CI** button.
New review comments on the PR/MR are sent too, with an **Address comments**
button: the agent that wrote the code works through them and pushes, so the
PR/MR updates.

## Run as a service (systemd, user)

```bash
dia service install     # writes ~/.config/systemd/user/dia.service, enables and starts it
echo 'DIA_DISCORD_TOKEN=paste-the-token' >> ~/.config/dia/env   # readable only by you
systemctl --user restart dia
dia service logs        # follow the journal; also: dia service status / uninstall
```

The service runs `dia serve` (Discord, voice, CI and review watching) from
login, restarts it on failure, and keeps the `PATH` you had when installing,
so the agents' CLIs are found.
