"""
PC Bridge — asyncio WebSocket + HTTP server.

Ports (configurable via config["bridge_port"], default 8082):
  WS:   bridge_port       — voice pipeline
  HTTP: bridge_port - 1   — /health, /roles, /sessions, /sessions/sync
  UDP:  broadcast → 8766  — auto-discovery beacon

Start via:
  threading.Thread(target=start_bridge, daemon=True).start()
"""
import asyncio
import base64
import json
import logging
import socket
import urllib.parse
from typing import Optional

log = logging.getLogger("bridge.server")

# Sentinel to signal end of LLM token stream
_DONE = object()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _send(ws, obj: dict):
    try:
        await ws.send(json.dumps(obj, ensure_ascii=False))
    except Exception:
        pass


def _parse_token(path: str) -> str:
    qs = path.split("?", 1)[1] if "?" in path else ""
    params = urllib.parse.parse_qs(qs)
    return params.get("token", [""])[0]


# ── STT ───────────────────────────────────────────────────────────────────────

def _transcribe_bytes(audio_bytes: bytes, lang: str) -> str:
    """Transcribe raw PCM 16 kHz mono int16 bytes → text using Whisper."""
    try:
        import numpy as np
        from services.ai.whisper import _load_whisper_model

        if not audio_bytes:
            return ""
        audio = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        model = _load_whisper_model()
        whisper_lang = None if lang.startswith("en") else lang[:2]
        segments, _ = model.transcribe(audio, language=whisper_lang, beam_size=5)
        return " ".join(seg.text for seg in segments).strip()
    except Exception as e:
        log.error("STT error: %s", e)
        return ""


# ── LLM ───────────────────────────────────────────────────────────────────────

def _run_llm_sync(session, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop) -> str:
    """Run Ollama (blocking) in a thread pool, forwarding tokens to the async queue."""
    from services.ai.ollama import chat_ollama

    def on_token(chunk: str):
        loop.call_soon_threadsafe(queue.put_nowait, chunk)

    try:
        result = chat_ollama(session.get_history(), on_token=on_token, mode=session.mode)
    except Exception as e:
        log.error("LLM error: %s", e)
        result = ""
    finally:
        loop.call_soon_threadsafe(queue.put_nowait, _DONE)
    return result


# ── TTS ───────────────────────────────────────────────────────────────────────

def _tts_bytes_sync(text: str, lang: str) -> bytes:
    from services.ai.tts import speak_to_bytes
    try:
        return speak_to_bytes(text, lang)
    except Exception as e:
        log.error("TTS error: %s", e)
        return b""


# ── Voice pipeline ────────────────────────────────────────────────────────────

async def _pipeline(ws, session, loop: asyncio.AbstractEventLoop):
    """Full round-trip: STT → LLM streaming → TTS → audio stream to mobile."""
    await _send(ws, {"type": "state", "state": "thinking"})

    # 1. STT
    audio_bytes = bytes(session.audio_buffer)
    session.reset_audio()

    transcript = await loop.run_in_executor(None, _transcribe_bytes, audio_bytes, session.lang)

    if not transcript.strip():
        await _send(ws, {"type": "state", "state": "listening"})
        return

    await _send(ws, {"type": "transcript", "text": transcript, "final": True})
    session.add_history("user", transcript)

    # 2. LLM streaming
    token_queue: asyncio.Queue = asyncio.Queue()
    llm_fut = loop.run_in_executor(None, _run_llm_sync, session, token_queue, loop)

    accumulated: list[str] = []
    while True:
        try:
            item = await asyncio.wait_for(token_queue.get(), timeout=60.0)
        except asyncio.TimeoutError:
            log.warning("LLM token stream timed out")
            break
        if item is _DONE:
            break
        accumulated.append(item)
        await _send(ws, {
            "type": "llm_chunk",
            "text": "".join(accumulated),
            "done": False,
        })

    response_text = "".join(accumulated)
    if not response_text.strip():
        await _send(ws, {"type": "state", "state": "listening"})
        return

    session.add_history("assistant", response_text)
    await _send(ws, {"type": "llm_chunk", "text": response_text, "done": True})

    # 3. TTS → stream audio chunks
    await _send(ws, {"type": "state", "state": "speaking"})
    audio_data = await loop.run_in_executor(None, _tts_bytes_sync, response_text, session.lang)

    if audio_data:
        chunk_size = 8192
        seq = 0
        for offset in range(0, len(audio_data), chunk_size):
            chunk = audio_data[offset : offset + chunk_size]
            await _send(ws, {
                "type": "audio_chunk",
                "data": base64.b64encode(chunk).decode(),
                "seq": seq,
            })
            seq += 1
        await _send(ws, {"type": "audio_end", "seq": seq})

    await _send(ws, {"type": "state", "state": "listening"})

    try:
        await llm_fut
    except Exception:
        pass


# ── WebSocket handler ─────────────────────────────────────────────────────────

async def _ws_handler(ws, path=None):
    """Handle one WebSocket connection."""
    from services.bridge.auth import validate_token
    from services.bridge.session import BridgeSession
    from storage.roles import load_roles

    actual_path = path or getattr(ws, "path", "/")
    token = _parse_token(actual_path)

    if not validate_token(token):
        log.warning("Bridge: rejected connection — bad token")
        await ws.close(4401, "Unauthorized")
        return

    loop = asyncio.get_event_loop()
    session = BridgeSession()
    roles = load_roles()

    log.info("Bridge: client connected, session=%s", session.session_id)
    await _send(ws, {
        "type": "session_ack",
        "session_id": session.session_id,
        "modes": list(roles.keys()),
    })
    await _send(ws, {"type": "state", "state": "listening"})

    pipeline_task: Optional[asyncio.Task] = None

    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except Exception:
                continue

            mtype = msg.get("type", "")

            if mtype == "session_start":
                session.mode = msg.get("mode", "negotiator")
                session.lang = msg.get("lang", "ru")
                log.debug("session_start: mode=%s lang=%s", session.mode, session.lang)
                await _send(ws, {"type": "state", "state": "listening"})

            elif mtype == "audio_chunk":
                data = base64.b64decode(msg.get("data", ""))
                session.audio_buffer.extend(data)

            elif mtype == "audio_end":
                if pipeline_task and not pipeline_task.done():
                    pipeline_task.cancel()
                pipeline_task = asyncio.create_task(_pipeline(ws, session, loop))

            elif mtype == "interrupt":
                session.interrupted = True
                if pipeline_task and not pipeline_task.done():
                    pipeline_task.cancel()
                await _send(ws, {"type": "state", "state": "listening"})

            elif mtype == "session_end":
                _persist_session(session)
                break

    except Exception as e:
        log.debug("Bridge WS error: %s", e)
    finally:
        if pipeline_task and not pipeline_task.done():
            pipeline_task.cancel()
        _persist_session(session)
        log.info("Bridge: client disconnected, session=%s", session.session_id)


def _persist_session(session):
    from storage.history import save_session
    if session.history:
        try:
            save_session(
                session.session_id,
                session.history,
                source="mobile",
                mode=session.mode,
            )
        except Exception as e:
            log.error("Failed to save bridge session: %s", e)


# ── HTTP server ───────────────────────────────────────────────────────────────

def _make_http_response(status: int, body: str) -> bytes:
    status_text = {200: "OK", 404: "Not Found", 405: "Method Not Allowed"}.get(status, "OK")
    body_bytes = body.encode("utf-8")
    headers = (
        f"HTTP/1.1 {status} {status_text}\r\n"
        f"Content-Type: application/json; charset=utf-8\r\n"
        f"Content-Length: {len(body_bytes)}\r\n"
        f"Access-Control-Allow-Origin: *\r\n"
        f"Connection: close\r\n\r\n"
    )
    return headers.encode() + body_bytes


async def _http_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    try:
        request_line = await asyncio.wait_for(reader.readline(), timeout=5.0)
        if not request_line:
            return
        parts = request_line.decode(errors="replace").split()
        if len(parts) < 2:
            return
        method, path = parts[0], parts[1]

        # Drain request headers
        while True:
            line = await asyncio.wait_for(reader.readline(), timeout=5.0)
            if line in (b"\r\n", b"\n", b""):
                break

        path_clean = path.split("?")[0]

        if path_clean == "/health":
            from services.ai.ollama import check_ollama, get_ollama_model
            model = get_ollama_model() if check_ollama() else "offline"
            body = json.dumps({"status": "ok", "model": model})
            writer.write(_make_http_response(200, body))

        elif path_clean == "/roles":
            from storage.roles import load_roles
            roles = load_roles()
            compact = {
                rid: {"name": r.get("name", rid), "color": r.get("color", "#89b4fa")}
                for rid, r in roles.items()
                if r.get("show_in_tray", True)
            }
            writer.write(_make_http_response(200, json.dumps(compact, ensure_ascii=False)))

        elif path_clean == "/sessions":
            from storage.history import load_sessions
            all_sessions = load_sessions()
            mobile = {
                sid: s for sid, s in all_sessions.items()
                if s.get("source") == "mobile"
            }
            items = sorted(
                mobile.items(),
                key=lambda x: x[1].get("updated", ""),
                reverse=True,
            )[:20]
            writer.write(_make_http_response(200, json.dumps(dict(items), ensure_ascii=False)))

        elif path_clean == "/sessions/sync" and method == "POST":
            raw_body = await asyncio.wait_for(reader.read(131072), timeout=10.0)
            try:
                data = json.loads(raw_body.decode("utf-8"))
                from storage.history import save_session
                for sid, sdata in data.items():
                    save_session(
                        sid,
                        sdata.get("history", []),
                        name=sdata.get("name"),
                        source=sdata.get("source", "mobile"),
                        mode=sdata.get("mode", ""),
                    )
                writer.write(_make_http_response(200, '{"status":"ok"}'))
            except Exception as e:
                writer.write(_make_http_response(200, json.dumps({"error": str(e)})))

        else:
            writer.write(_make_http_response(404, '{"error":"not found"}'))

        await writer.drain()
    except Exception as e:
        log.debug("HTTP handler error: %s", e)
    finally:
        try:
            writer.close()
        except Exception:
            pass


# ── UDP Discovery Beacon ──────────────────────────────────────────────────────

async def _udp_beacon(ws_port: int, beacon_port: int = 8766):
    """Broadcast a UDP packet every 5 s so the mobile app can find the PC."""
    payload = json.dumps({"service": "ut-bridge", "port": ws_port}).encode()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setblocking(False)
    try:
        while True:
            await asyncio.sleep(5)
            try:
                sock.sendto(payload, ("<broadcast>", beacon_port))
            except Exception as e:
                log.debug("Beacon send error: %s", e)
    finally:
        sock.close()


# ── Entry point ───────────────────────────────────────────────────────────────

def start_bridge():
    """
    Run the bridge asyncio event loop.
    Must be called in a daemon thread from main.py.
    """
    try:
        import websockets  # noqa: F401
    except ImportError:
        log.error(
            "websockets package not installed — bridge disabled. "
            "Run: pip install websockets"
        )
        return

    import websockets as _ws_lib

    from config import config
    from globals import stop_event as _stop_event

    ws_port   = int(config.get("bridge_port", 8082))
    http_port = ws_port + 1  # 8083 by default (avoids Metro bundler port 8081)

    async def _run():
        # WebSocket server
        try:
            ws_server = await _ws_lib.serve(_ws_handler, "0.0.0.0", ws_port)
            log.info("Bridge WebSocket listening on 0.0.0.0:%d", ws_port)
        except Exception as e:
            log.error("Cannot start WS server on port %d: %s", ws_port, e)
            return

        # HTTP server
        http_server = None
        try:
            http_server = await asyncio.start_server(_http_handler, "0.0.0.0", http_port)
            log.info("Bridge HTTP listening on 0.0.0.0:%d", http_port)
        except Exception as e:
            log.warning("Cannot start HTTP server on port %d: %s", http_port, e)

        beacon_task = asyncio.create_task(_udp_beacon(ws_port))

        # Run until the main app signals shutdown
        while not _stop_event.is_set():
            await asyncio.sleep(1)

        log.info("Bridge shutting down")
        beacon_task.cancel()
        ws_server.close()
        await ws_server.wait_closed()
        if http_server:
            http_server.close()
            await http_server.wait_closed()

    asyncio.run(_run())
