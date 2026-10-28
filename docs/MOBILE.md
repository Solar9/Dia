# Dia on your phone

The web UI works as an installable app (PWA) on Android and iOS: tasks,
chat, status, approvals (merge, PR/MR, fixes) and learned facts. Your
computer keeps doing the work; the phone only talks to `dia serve`.

## 1. Reach the computer privately: Tailscale (recommended)

Dia must never be open to the internet. The simplest safe way is
[Tailscale](https://tailscale.com) (free for personal use) on the computer
and the phone, then on the computer:

```sh
sudo tailscale serve --bg 8765    # https://<computer>.<tailnet>.ts.net → 127.0.0.1:8765
```

This gives Dia an HTTPS address that only your devices can open. HTTPS
matters: phones install a web app (and keep it working offline) only from
an HTTPS address.

## 2. Allow paired devices

In `~/.config/dia/config.toml`:

```toml
[ui]
remote = true
public_url = "https://laptop.tail1234.ts.net"   # the address from `tailscale serve`
hosts = ["laptop.tail1234.ts.net"]              # Host names Dia answers to
# listen = ["100.101.102.103"]   # instead of `tailscale serve`: also listen on this
#                                # address (plain HTTP; only on a private network)
```

Restart Dia (`dia service restart`, or restart `dia serve`).

## 3. Pair the phone

```sh
pip install 'dia[mobile]'      # optional: QR codes
dia mobile pair --name phone
```

Scan the QR code with the phone (or open the printed link), then
"Install app" / "Add to Home Screen". The same is in the UI: Settings →
Devices → Pair.

- `dia mobile list`: paired devices and when they were last used.
- `dia mobile revoke phone`: the device's token stops working at once
  (also Settings → Devices).

## What a device may do

A paired device has its own token (Dia stores only its hash). It can see
and start tasks, chat, approve merges and PRs/MRs, run fixes and accept
learned facts. It **cannot** read or change the configuration (an agent's
command line could be changed into anything), use the computer's
microphone, or pair and revoke devices: those only work on the computer
itself, with the owner token. The owner token is refused when a request
does not come from this computer, even through `tailscale serve`.

**Talking on the phone**: the microphone button in the middle of the phone's
bottom bar opens a conversation that uses the phone's own microphone, never
the computer's. The phone records you (16 kHz WAV, up to 30 s, it stops when
you pause) and sends the recording to your Dia (`POST /api/talk`); Dia's own
speech recognition hears it, the text goes to Dia like a chat message (in the
current chat session), and the answer comes back as text and as speech in
Dia's own voice, played on the phone (text only in quiet mode). It uses the
`stt` and `tts` of `[channels.voice]` (local Whisper and Piper by default,
docs/VOICE.md), so nothing leaves your computer; it works without the voice
channel itself running, with `pip install 'dia[voice]'`. Without speech
recognition on the computer the phone falls back to the browser's own
dictation where there is one (Chrome and Safari send it to Google or Apple),
and otherwise offers "Write instead". The app asks for the microphone the
first time (Android: RECORD_AUDIO; iOS: NSMicrophoneUsageDescription).

**Full access** for your own phone: Settings → Devices → "full access" next
to it (set on the computer only). Such a phone also changes settings,
projects and agents, edits the config file and runs Dia's tools (Status →
Tools), so the app on the phone does everything the desktop app does,
except two things that stay on the computer: secrets and pairing devices.
Turn it off for any phone you lend out.

## The Android and iOS app

`mobile/` is Dia's native app for Android and iOS (Capacitor). It holds no
copy of Dia: it pairs with *your* Dia and shows its interface, with the app
icon, a splash screen, and a QR scanner for pairing.

1. On the computer: Settings → Devices → pair a device (as in step 3 above).
2. On the phone: open the app, **Scan the QR code** (or paste the pairing
   link). It remembers your Dia; "Change server" at the bottom of the menu
   goes back to pairing.

The phone must reach your Dia: the same Wi-Fi, Tailscale (step 1), or
another tunnel.

### Getting the app

- **Android, without the store**: every release has `dia-<version>-android.apk`
  (and every change to `mobile/` builds a debug APK as a CI artifact).
  It needs Android 8.0 or newer.
  Install it after allowing installs from your browser or files app.
- Release APKs require all four signing secrets below. Without any of them a
  release tag attaches the debug APK (`dia-<version>-android-debug.apk`, for
  testing only, no AAB) instead of an unsigned, un-installable one; with only
  some of them the job fails.
  For testing, download `dia-debug-apk` from a successful **Mobile app** run
  in GitHub Actions, extract the ZIP and install `app-debug.apk`. Debug
  signing keys can change between CI runs; this is not a stable update channel.
  To rebuild the test APK manually, use GitHub → Actions → **Mobile app** →
  **Run workflow** on `main`. Download `dia-debug-apk` from the completed run
  and extract it. Debug builds do not require release signing secrets.
- **Building it yourself**: Node 22, then

  ```bash
  cd mobile && npm ci && npx cap sync
  npx cap open android     # Android Studio: Run, or Build → Generate signed bundle
  npx cap open ios         # Xcode on a Mac: Product → Archive
  ```

  The icons and splash screens come from `mobile/resources/` (rendered from
  `assets/dia.svg` by `node assets/render-icons.js`; then `npm run assets`).

### Publishing in Google Play

1. A Google Play developer account (one-time fee) and an upload key:
   `keytool -genkey -v -keystore dia.jks -alias dia -keyalg RSA -keysize 2048 -validity 10000`.
2. GitHub → Settings → Secrets → Actions: `DIA_ANDROID_KEYSTORE_BASE64`
   (`base64 -w0 dia.jks`), `DIA_ANDROID_KEYSTORE_PASSWORD`,
   `DIA_ANDROID_KEY_ALIAS`, `DIA_ANDROID_KEY_PASSWORD`. The next release tag
   builds a signed `dia-<version>-android.aab`.
   Keep a private backup of the keystore and reuse it for future releases so
   Android can install updates over the existing app. CI verifies the APK
   signature with `apksigner` before uploading it.
3. Play Console: create the app (package `io.github.solar9.dia`), upload the
   AAB to internal testing first, fill in the store listing (the icon:
   `mobile/resources/icon.png`), the Data safety form (the app sends data only
   to the user's own Dia server; camera for the QR code only) and a privacy
   policy URL.

### Publishing in the App Store

1. An Apple Developer Program membership and a Mac with Xcode.
2. `cd mobile && npm ci && npx cap sync ios && npx cap open ios`; set your Team
   in Signing & Capabilities (bundle id `io.github.solar9.dia`), then Product →
   Archive → Distribute App → App Store Connect.
3. App Store Connect: the listing, privacy details (as above) and review notes:
   the reviewer needs a Dia to pair with, so give them a test server and its
   pairing link, or the review will stop at the pairing screen. Apple reviews
   apps that mostly show a website strictly (guideline 4.2); the native
   pairing and scanning help, but expect questions.

What the app does not do yet: push notifications while it is closed (that
needs Firebase/APNs credentials of your own; the installed web app from
step 3 has them through Web Push).
