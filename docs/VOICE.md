# Voice

Press a shortcut, speak, press it again: Dia transcribes what you said, its
brain decides what to do, and it answers out loud. Tasks keep running in the
background and Dia speaks again when they finish. Pressing the shortcut while
Dia is talking interrupts her and starts listening.

Everything runs locally: speech recognition with Whisper (faster-whisper),
speech with Piper, the optional wake word with openWakeWord. Only the request itself goes to whichever brain/agent you
configured.

## 1. Install

```bash
pip install -e '.[voice]'        # faster-whisper + piper-tts
```

Recording and playback use your system's audio tools, detected automatically:
PipeWire (`pw-record`/`pw-play`, standard on current KDE and GNOME),
PulseAudio (`parecord`/`paplay`), ALSA (`arecord`/`aplay`) or ffmpeg.
Desktop notifications use `notify-send` when available.

## 2. Configure

```toml
[channels.voice]
type = "voice"
language = "pl"                       # also the language of Dia's own phrases (pl, en)
stt = { type = "faster-whisper", model = "small" }   # "medium": better, slower
tts = { type = "piper", voice = "pl_PL-gosia-medium" } # or pl_PL-darkman-medium, ...
# speak_max_chars = 400               # longer answers are cut at a sentence end
# notifications = true
# record_command = ["pw-record", "--rate", "16000", "--channels", "1", "{output}"]
# play_command = ["pw-play", "{input}"]
```

The Whisper model and the Piper voice are downloaded on first use (to
`~/.cache/huggingface` and `~/.local/share/dia/voices`).

Any other engine works through `type = "command"`, for example
whisper.cpp for recognition or espeak-ng for speech:

```toml
stt = { type = "command", argv = ["whisper-cli", "-m", "/path/ggml-small.bin", "-l", "{language}", "-nt", "-np", "-f", "{audio}"] }
tts = { type = "command", argv = ["espeak-ng", "-v", "pl", "-w", "{output}", "{text}"] }
```

## 3. Test

```bash
dia voice speak "Cześć, tu Dia."     # do you hear the voice?
dia voice listen --seconds 5         # speak; prints what Whisper understood
dia doctor                           # "channel voice  ok"
dia serve                            # runs voice (and Discord, if configured)
dia voice toggle                     # from another terminal: start / stop listening
```

## 4. Bind the shortcut

Use the full path of `dia` (e.g. `~/dia/.venv/bin/dia`; `which dia` shows it).

| Desktop | Where |
|---------|-------|
| **KDE Plasma** | System Settings → Keyboard → Shortcuts → **Add New → Command or Script…** → command `/home/you/dia/.venv/bin/dia voice toggle`, then assign a key (e.g. Meta+D) |
| **GNOME** | Settings → Keyboard → View and Customize Shortcuts → **Custom Shortcuts** → + |
| **Xfce** | Settings → Keyboard → **Application Shortcuts** → Add |
| **Cinnamon / MATE** | Keyboard → Shortcuts → **Custom Shortcuts** |
| **Hyprland** | `bind = SUPER, D, exec, ~/dia/.venv/bin/dia voice toggle` |
| **Sway / i3** | `bindsym $mod+d exec ~/dia/.venv/bin/dia voice toggle` |

This works the same on Wayland and X11, because the desktop owns the key and
Dia only receives a command over a private socket
(`$XDG_RUNTIME_DIR/dia/voice.sock`, readable only by you).

Other commands: `dia voice start`, `dia voice stop` (for desktops that can
bind key press and release separately, i.e. real push-to-talk) and
`dia voice cancel` (stop listening or talking without doing anything).

## Troubleshooting

- **"the recording is silent" / "Mikrofon nagrał samą ciszę"**: the default
  input is muted or is another device (e.g. a disconnected headset). Pick the
  right input in your sound settings (`pactl get-default-source` shows it).
- **Slow replies**: recognition with `small` takes a few seconds on a laptop
  CPU; requests the rules don't recognise also go through the brain. `base`
  is faster but less accurate; a local brain (Ollama) avoids the network trip.
- **Words not recognised**: say the request after a short pause; "Dia,
  status" works even when recognised as "Dias status" or "Dziastatus".

## 5. Wake word (optional)

Instead of (or as well as) the shortcut, say a wake word; Dia records until
you stop talking. Detection runs locally with openWakeWord, which is light
enough for a laptop CPU, and pauses while Dia herself speaks.

```bash
pip install -e '.[wake]'
# openWakeWord's own package pins tflite-runtime, which has no builds for
# Python 3.13; Dia uses its ONNX models, so install it without that pin:
pip install --no-deps openwakeword==0.6.0
```

```toml
[channels.voice]
# ... as above, plus:
wake = { type = "openwakeword", model = "hey_jarvis", threshold = 0.5 }
# silence_seconds = 0.8      # pause that ends your request
# wait_seconds = 5           # give up if nothing is said after the wake word
# max_seconds = 15
```

Ready-made models: `hey_jarvis`, `hey_mycroft`, `alexa`, `hey_rhasspy`
(downloaded on first use). For **"Hey Dia"**, train your own model with
openWakeWord's training notebook (it generates synthetic samples, no
recording needed; see "Training New Models" in the openWakeWord README) and
point `model` at the resulting `.onnx` file:

```toml
wake = { type = "openwakeword", model = "~/.local/share/dia/hey_dia.onnx" }
```

### "Hej Dia" without training

The `whisper-keyword` detector needs no model of its own: short stretches of
speech are transcribed by a tiny Whisper model and matched against the
keyword. You can also say the request in one breath, "Hej Dia, jaka
pogoda?", and Dia answers it right away.

```toml
wake = { type = "whisper-keyword", language = "pl" }
# keyword = "\\b(?:hej\\s+)?dia\\b"   # a regular expression
# model = "tiny"                      # "base" hears better, costs more CPU
```

It uses more CPU than openWakeWord while someone talks (none while it is
quiet); openWakeWord with a trained "hey dia" model stays the lightest.

### Talking with Dia

Long answers start at once: Dia speaks sentence by sentence while the next
one is prepared. Press the shortcut while she talks to interrupt her; she
stops the whole answer and listens. Replies are written for being heard
(short, no lists); quiet mode ("tryb cichy") keeps her silent.

Raise `threshold` if it wakes up by itself, lower it if it misses you. With
the wake word on, the microphone stays open while `dia serve` runs (only on
your machine; nothing is sent anywhere until the wake word is heard), and
the shortcut uses the same stream.

### Who is speaking

With speaker recognition Dia knows your voice (and others you enroll), and a
voice it doesn't know may only chat, ask for the weather, news and markets,
and hear the status: no tasks, programs, house, mail, calendar, screen or
camera.

```sh
pip install sherpa-onnx
# a speaker embedding model, e.g. 3D-Speaker eres2net, from the sherpa-onnx
# releases ("speaker-recongition-models"), saved as ~/.local/share/dia/speaker.onnx
dia voice enroll Dawid     # three times a few sentences
dia voice speakers         # who Dia knows; dia voice forget NAME
```

```toml
[channels.voice]
speaker = { type = "sherpa-onnx", model = "~/.local/share/dia/speaker.onnx" }
# threshold = 0.5, unknown = "limited" | "ignore" | "allow"
# guest_skills = ["weather", "news", "stocks"]
```

Voices are kept as numbers (embeddings), not recordings. Recognition avoids
mistakes in a shared room; it is not a lock (a recording of your voice can
fool it), and approvals stay buttons.

## What to say

Anything the brain understands, e.g.:

- "Dia, status" / "zadania" (handled instantly, without a model)
- "Którym przyciskiem strzela gracz w Nova?" (a read-only question)
- "Dodaj w Nova sterowanie padem, strzelanie pod prawym spustem" (a task on
  its own branch; approve it with `dia merge`, or the Discord buttons)
- "Zaprojektuj z Claude i zbuduj z Codexem system craftingu w Nova" (a plan)
- "Odpal Nova" (starts the game)

Merging and discarding are never done by voice.
