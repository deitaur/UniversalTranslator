# AI Companion — Mobile App

React Native (Expo) app that connects to the home PC via WebSocket for voice AI sessions while walking.

## Setup

```bash
cd mobile
npm install
npx expo start
```

Scan the QR with the Expo Go app (Android/iOS), or build for device:

```bash
npx eas build --platform android --profile preview
```

## Connecting to PC

1. Open Universal Translator on your PC
2. Go to **Settings → Mobile Bridge** and enable it
3. Note the QR code or copy the token
4. Open the app → Onboarding → enter your PC's local IP + token
5. Tap **Test Connection** — should show ✓

## Architecture

```
Mobile (Expo)
  app/           — Expo Router screens
  src/
    state/       — XState FSM + Zustand stores
    services/    — WebSocket bridge client, cloud AI, audio pipeline
    components/  — ModeSelector, WalkTimer

PC (Python)
  services/bridge/
    server.py    — asyncio WS + HTTP server (port 8082 / 8764)
    auth.py      — HMAC token validation
    session.py   — per-connection state
```

## PC Bridge ports

| Port | Protocol | Purpose |
|------|----------|---------|
| 8082 | WebSocket | Voice pipeline (audio → STT → LLM → TTS) |
| 8083 | HTTP      | /health, /roles, /sessions |
| 8766 | UDP broadcast | Auto-discovery beacon |

## New pip packages required (PC)

```bash
pip install websockets qrcode[pil]
```

## Voice flow

```
IDLE → LISTENING → PROCESSING_STT → PROCESSING_LLM → SPEAKING → LISTENING
```

Double-tap orb to interrupt AI and start speaking again.
