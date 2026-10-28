# Dia as an everyday assistant

Besides running coding agents, Dia answers everyday questions, keeps a
schedule and talks with the voice and personality you choose. Everything
here can be set in the UI (Settings) or in the config file.

## Who Dia is

```toml
[assistant]
name = "Dia"
user_name = "..."            # how Dia addresses you
personality = "butler"       # friendly | butler | concise | buddy | mentor | your own text
```

The persona goes into every model prompt, so chat answers, plans and spoken
replies all sound the same. A personality can be any description: "calm,
dry humour, speaks like a ship's captain".

## Skills: weather, news, markets, briefing

Ask in your own words ("Dia, jaka jutro pogoda w Gdańsku?", "co nowego?",
"jak tam giełda?", "dzień dobry") on any channel. Fixed phrases are handled
without a model call; anything else is routed by the brain.

```toml
[skills.weather]
place = "Kraków"                 # or latitude/longitude; Open-Meteo, no key

[skills.news]
feeds = ["https://tvn24.pl/najnowsze.xml", "https://www.rmf24.pl/fakty/feed"]
count = 5

[skills.stocks]
symbols = ["AAPL", "CDR.WA", "^GSPC"]    # Yahoo symbols; source = "stooq" for Stooq

[skills.crypto]
coins = ["btc", "eth", "sol"]            # tickers or CoinGecko ids
currency = "pln"                         # default: usd
```

"Kursy krypto", "ile kosztuje bitcoin?" or `dia skill crypto` give the
prices with their 24 h change (CoinGecko, no key).

The **briefing** combines the weather, what your agents did since yesterday
(and what waits for your decision), news and markets:
`[skills.briefing] sections = ["weather", "work", "news", "stocks", "crypto"]`.

Skills are plugins (`dia.skills`): a class with `description`, `args` and
`async run(args) -> str`. See docs/ARCHITECTURE.md.

## Schedule

```sh
dia schedule add "30 7 * * 1-5" "briefing" --speak    # weekdays 7:30, read aloud
dia schedule add "0 23 * * *" "sprawdź czy wszystkie projekty mają backup"
dia schedule                                          # list with the next run
```

or just tell Dia: "codziennie o 7:30 w dni robocze daj mi briefing". Jobs
run while `dia serve` runs; answers go to Discord, push and the UI. A job
can also run a task (`action = "task"`) or a skill directly; see
`[[schedule]]` in dia.example.toml.

## Voice: Piper or ElevenLabs

Piper (local, free) is the default. For an ElevenLabs voice, including one
you created or cloned in your ElevenLabs account:

```sh
dia secret set ELEVENLABS_API_KEY
```

```toml
[channels.voice]
tts = { type = "elevenlabs", voice_id = "<from your voice library>", fallback = "piper" }
```

`fallback` speaks when ElevenLabs can't (offline, out of credits). Cloning
someone's voice needs that person's consent; ElevenLabs asks for it when
the voice is created. Try it with `dia voice speak "Cześć"`.

## Secrets

API keys and tokens live only in `~/.config/dia/env` (mode 600), the file
the systemd service reads. `dia secret set NAME` (hidden input), `dia
secret list` (names only), `dia secret rm NAME`, or Settings → Secrets.
Values are never shown again, never stored in the config or the repository.

## Local brain (Ollama)

A small local model understands requests for free and privately; the
subscription model stays as a fallback. On Arch:

```sh
sudo pacman -S ollama && sudo systemctl enable --now ollama
ollama pull qwen3.5:4b          # routing (best measured 25.10.2026: 8/9; ~2–3 GB)
ollama pull nomic-embed-text    # semantic memory search (optional)
```

Then Settings → Voice & brain → Local brain, or:

```toml
[dia]
brain = ["rules", "local", "default-agent"]

[brains.local]
type = "ollama"
model = "qwen3.5:4b"
```

`dia brains --test "jaka pogoda w Krakowie"` shows what each brain makes of a
message and how long it takes. Before putting a new local model first,
`dia brains --replay 50 --brain local` gives it your last 50 real requests
(without executing anything) and shows how often it decides the same as
the brain that handled them. The requests are kept in Dia's local database
for this; `[assistant] log_intents = false` turns that off. See
[MEASUREMENT.md](MEASUREMENT.md).

## Plain chat with Claude or ChatGPT

In the app's Chat, each conversation can talk to **Dia** (the assistant:
tasks, skills, plans) or **straight to a model**, like the Claude or
ChatGPT apps, which is cheaper and faster for everyday questions. Pick it
at the top of the conversation, with the model next to it:

- **Claude**, **ChatGPT** and **Cursor** (subscription): your Claude Code,
  Codex and Cursor agents, without tools, in an empty folder, so answers
  count against your subscription, not an API bill. Models: `sonnet`,
  `opus`, `haiku` for Claude; for Codex, list the ones your plan offers:

  ```toml
  [chat]
  default = "dia"                          # what a new conversation talks to
  models = { codex = ["gpt-5", "gpt-5-mini"] }   # per agent name
  ```

- **Claude API** with `ANTHROPIC_API_KEY` (`pip install 'dia[chat]'`, the
  official SDK), **OpenAI API** with `OPENAI_API_KEY`: paid per token, with
  the model list read from the API. A request Claude declines for policy
  reasons is retried on its server-side fallback model.
- **Ollama**, local and free, when it is running (`[chat] ollama_url`).

The main conversation (shared with voice and Discord) always talks to Dia.

## Memory that finds by meaning

```toml
[memory]
semantic = { model = "nomic-embed-text" }   # any OpenAI-compatible /embeddings
```

`dia memory index` builds the index (`dia serve` keeps it fresh); searches
then combine meaning and keywords. Embeddings are made locally by Ollama, so
the notes stay on the computer.

## Issues → tasks

```toml
[issues]
label = "dia"          # open issues with this label become plans
planner = false        # true: let the planner agent split them into steps
```

While `dia serve` runs (or with `dia issues`), each new labelled issue on
GitHub/GitLab becomes a plan waiting for your approval; its PR/MR says
"Closes #N". Only maintainers can label issues, and nothing runs until you
press Run.

## Notifications and usage

- Settings → Devices → Notifications: push to the phone or desktop app
  (`pip install 'dia[push]'`, HTTPS e.g. via Tailscale; see docs/MOBILE.md).
- The Usage view (or `dia usage`): calls per agent and per day, success
  rate, time and usage limits hit.

## Your preferences

"Dia, zapamiętaj, że wolę krótkie odpowiedzi" keeps a preference at once.
Preferences go into every prompt: how Dia answers you and the background
every coding agent gets ("type hints everywhere", "testy w GUT").

```toml
[assistant]
preferences = ["Uses Godot 4.x"]   # fixed ones, from the config
learn_preferences = true           # notice them in conversations
learn_every = 10                   # ... every 10 exchanges, one cheap call
```

With `learn_preferences`, Dia proposes what looks like a lasting preference;
nothing is used before you accept it (Memory → Your preferences, or
`dia preferences --accept 1`). Remove one there or with `dia preferences
--remove N`. They are kept in `<data_dir>/preferences.json`.

## How-tos (procedural memory)

After a task went well, "Dia, zapamiętaj, jak to zrobiłeś" (or **Remember
how** on the task, or `dia howto <task>`) has an agent write down how it
was done as a reusable procedure. You see it first and keep it with a yes
(**Keep**, `dia howto <task> --save`). It is stored as a note in
`<vault>/Dia/How-tos/` with a `when:` line in its frontmatter; you can edit
it like any note.

When a later task on that project matches the how-to's title or `when`
words ("dodaj nowego przeciwnika"), the agent gets the procedure with its
instructions. `dia howto` lists them. Needs `[memory]`.

## Notion

Create an internal integration at notion.so/my-integrations, share the pages
Dia may use with it (⋯ → Connections), and save its token with `dia secret
set NOTION_TOKEN`. Then "co mam w Notion o bossach?", "przeczytaj stronę
pomysły na Nova", "dodaj do Notion notatkę: smok w lochu 3".

```toml
[skills.notion]
parent = "<page id>"           # where new notes go (the id from the page's link)
# parent_is_database = true    # if it is a database
# title_property = "Name"      # the database's title column
```

## Quiet hours and a notification budget

```toml
[notifications]
quiet_hours = "22:00-07:30"   # Dia says nothing on its own and sends no push
budget = 20                   # push notifications a day, at most
urgent = ["system", "security", "stop"]   # always get through
```

Nothing is lost: what was held comes as one summary when quiet hours end
(push "Dia: while it was quiet"), and `GET /api/notifications` lists it.
Answers to what you ask are never held; to silence speech entirely use quiet
mode ("tryb cichy"). The sidebar shows 🌙 during quiet hours.

## Research reports

"Dia, zrób research: jak gry roguelike robią sieć dla co-opa?" (or `dia
research [project] "topic"`, Inbox/Tasks → Research in the composer) has an agent with web access
(Claude Code's WebSearch/WebFetch, Codex's web search) read sources and write
a report with links: summary, findings, what it means for the project, open
questions. It is a task, and with memory on also a note in
`<vault>/Dia/Research/`, so later tasks can find it. `[research] agent` picks
the agent (one with web access). Check the sources: it is a starting point.

## Clipboard

"co mam w schowku?", "przetłumacz schowek na angielski", "popraw tekst w
schowku", "skopiuj mi ten link": Dia reads the clipboard only when you ask
(each read is in the audit log) and puts a changed text back, ready to paste.
Needs wl-clipboard (Wayland) or xclip.
