# Integrations

Secrets (tokens, passwords, private addresses) always go to `dia secret set
NAME` or Settings → Secrets, never to the config.

## Calendar (Google Calendar or any iCal)

Google Calendar → Settings → your calendar → "Secret address in iCal
format". Then `dia secret set DIA_CALENDAR_URL` and paste it. Read-only.
"co mam dziś?", "co mam jutro?", and the morning briefing.
Several calendars: `[skills.calendar] url_secrets = ["DIA_CALENDAR_URL", "WORK_CALENDAR_URL"]`.

## Mail (Gmail or any IMAP)

```toml
[skills.mail]
host = "imap.gmail.com"
user = "you@gmail.com"
```

`dia secret set DIA_MAIL_PASSWORD` (for Gmail an app password: Google
account → Security → App passwords). "czy mam maile?" and the briefing list
unread messages. Read-only: nothing is marked read, sent or deleted.

## Home Assistant

```toml
[skills.home]
url = "http://homeassistant.local:8123"
```

`dia secret set HA_TOKEN` (Home Assistant → your profile → Long-lived access
tokens). "włącz światło na biurku", "tryb pracy" (a scene), "czy drzwi są
zamknięte?". Locks, alarms, covers and garage doors ask for a yes first.
"Tryb pracy" can also be a scheduled job: `dia schedule add "0 9 * * 1-5" "włącz scenę tryb pracy"`.

## Notion

See [ASSISTANT.md](ASSISTANT.md#notion): the secret NOTION_TOKEN and
`[skills.notion] parent`.

## itch.io

```toml
[builds]
itch = "yourname/nova"
itch_channels = { "Linux" = "linux", "Windows Desktop" = "windows" }
```

Install [butler](https://itch.io/docs/butler/) and run `butler login` (or
`dia secret set BUTLER_API_KEY`). A finished build is published only when
you press **Publish on itch.io** on it, or run `dia publish-build <task>`.

## Steam

`[builds.steam]` and **Publish on Steam**: see
[COMPUTER.md](COMPUTER.md#steam). Never live on the default branch.
