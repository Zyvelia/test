# CharChat — Flutter iOS App

Character chat frontend for Ollama running on your local network PC.

---

## Requirements

- Flutter 3.19+ (`flutter --version`)
- Xcode 15+ (for iOS build)
- Ollama running on your PC with at least one model pulled
- Your PC and iPhone on the same WiFi network

---

## Setup

### 1. Install dependencies
```bash
cd charchat_flutter
flutter pub get
```

### 2. Find your PC's local IP
On Windows: `ipconfig` → look for IPv4 under your WiFi adapter (e.g. `192.168.1.42`)  
On Mac: `ifconfig | grep 192`

### 3. Make Ollama reachable on the network
By default Ollama only listens on localhost. Run it with:
```
OLLAMA_HOST=0.0.0.0 ollama serve
```
Or on Windows, set the environment variable `OLLAMA_HOST=0.0.0.0` before starting Ollama.

### 4. Build for iOS

**Via Xcode (real device or TrollStore):**
```bash
cd ios
open Runner.xcworkspace
```
Set your Team in Signing & Capabilities, select your device, hit Run.

**Via command line:**
```bash
flutter build ios --release
```
Then open `build/ios/iphoneos/Runner.app` in Xcode for device deployment.

**TrollStore (no paid dev account):**
```bash
flutter build ios --release --no-codesign
# produces an .ipa via the usual TrollStore sideload workflow
```

---

## First launch

1. App opens → create account (username, email, password — stored on-device only, never sent anywhere)
2. Go to **Settings** → enter your PC's IP: `http://192.168.1.x:11434`
3. Tap **Fetch** to see available models, or type one manually
4. Tap **Save**
5. Go to **Characters** → create or import a character
6. Tap **Chat** → start talking

---

## Features

- **Characters** — create, edit, delete; per-character NSFW toggle; AI auto-fill for all fields
- **Chat** — streaming responses, CAI-style `*action*` rendering, regenerate last reply
- **Memory** — auto-extracts facts from conversations every 6 messages; manual add/delete
- **Personas** — define who you are; character sees your name, appearance, backstory, traits
- **Settings** — Ollama URL, model, response style (concise/balanced/verbose), context window size
- **Auth** — local password with salted SHA-256 (10k rounds), lockout after 5 failures

---

## Data

All data lives in the app's Documents directory — no cloud, no external servers.  
Characters, personas, chat logs, memories: `~/Documents/charchat/`

---

## Ollama connection troubleshooting

In the app: **Settings → Test connection** tells you exactly what is wrong.

- **iOS says blocked / "Operation not permitted"**: iPhone Settings → CharChat → enable **Local Network**
- The GitHub workflow regenerates `ios/`, so it patches `Info.plist` itself (local network + HTTP). Edit the "Patch Info.plist" step in `.github/workflows/ios.yml`, not `ios/Runner/Info.plist`.
- Test from Safari on the phone: `http://PC-IP:11434` should show "Ollama is running".


- **Connection refused**: Ollama not running, or not bound to `0.0.0.0`
- **Timeout**: Wrong IP, or firewall blocking port 11434 on the PC
- **Model not found**: Model name must match exactly — use Fetch to see installed models
- **Slow**: First response after idle takes a few seconds for the model to load into VRAM; subsequent turns are faster

## iOS CI build

The repository intentionally does **not** contain Flutter-generated iOS state such as
`ios/Flutter/ephemeral`, `.dart_tool`, `Generated.xcconfig`, or generated plugin registrants.
GitHub Actions regenerates these files with the stable Flutter toolchain before building.
