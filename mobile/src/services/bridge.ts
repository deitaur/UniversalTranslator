/**
 * WebSocket client — connects to the PC Bridge.
 * Handles reconnection and dispatches FSM events via a provided callback.
 */
import { SessionEvent } from '@/state/sessionMachine';

type MessageCallback = (event: SessionEvent) => void;
type RawCallback     = (msg: Record<string, unknown>) => void;

let _ws: WebSocket | null = null;
let _reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let _onMessage: MessageCallback | null = null;
let _onRaw:     RawCallback     | null = null;
let _url: string = '';

export function connectBridge(
  url: string,
  onMessage: MessageCallback,
  onRawMessage?: RawCallback,
): void {
  _url = url;
  _onMessage = onMessage;
  _onRaw = onRawMessage ?? null;
  _connect();
}

export function disconnectBridge(): void {
  if (_reconnectTimer) clearTimeout(_reconnectTimer);
  _ws?.close();
  _ws = null;
}

export function sendBridgeMessage(obj: object): void {
  if (_ws?.readyState === WebSocket.OPEN) {
    _ws.send(JSON.stringify(obj));
  }
}

export function sendAudioChunk(pcmInt16Base64: string): void {
  sendBridgeMessage({ type: 'audio_chunk', data: pcmInt16Base64 });
}

export function sendAudioEnd(): void {
  sendBridgeMessage({ type: 'audio_end' });
}

export function sendInterrupt(): void {
  sendBridgeMessage({ type: 'interrupt' });
}

export function sendSessionEnd(): void {
  sendBridgeMessage({ type: 'session_end' });
}

export async function testConnection(url: string): Promise<boolean> {
  return new Promise((resolve) => {
    const timeout = setTimeout(() => { ws.close(); resolve(false); }, 4000);
    const ws = new WebSocket(url);
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === 'session_ack') {
          clearTimeout(timeout);
          ws.close();
          resolve(true);
        }
      } catch {}
    };
    ws.onerror = () => { clearTimeout(timeout); resolve(false); };
  });
}

function _connect(): void {
  if (!_url) return;

  _ws = new WebSocket(_url);

  _ws.onopen = () => {
    console.log('[bridge] connected');
    if (_reconnectTimer) { clearTimeout(_reconnectTimer); _reconnectTimer = null; }
  };

  _ws.onmessage = (e) => {
    if (!_onMessage) return;
    try {
      const msg = JSON.parse(e.data as string);
      const evt = _mapToFsmEvent(msg);
      if (evt) _onMessage(evt);
    } catch {}
  };

  _ws.onclose = () => {
    console.log('[bridge] disconnected — reconnecting in 3s');
    _onMessage?.({ type: 'RECONNECTING' });
    _reconnectTimer = setTimeout(_connect, 3000);
  };

  _ws.onerror = () => {
    _ws?.close();
  };
}

function _mapToFsmEvent(msg: Record<string, unknown>): SessionEvent | null {
  switch (msg.type) {
    case 'session_ack':
      return { type: 'SESSION_ACK', sessionId: msg.session_id as string };
    case 'transcript':
      return { type: 'TRANSCRIPT', text: msg.text as string };
    case 'llm_chunk':
      return { type: 'LLM_CHUNK', text: msg.text as string, done: msg.done as boolean };
    case 'audio_chunk':
      return { type: 'AUDIO_CHUNK' };
    case 'audio_end':
      return { type: 'AUDIO_END_TTS' };
    case 'state':
      return { type: 'STATE', state: msg.state as 'listening' | 'thinking' | 'speaking' };
    default:
      return null;
  }
}
