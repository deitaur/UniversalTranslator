/**
 * Cloud AI fallback — Gemini API (primary) → Claude API (secondary).
 * Used when the PC Bridge is unreachable.
 */
import { useConnectionStore } from '@/state/connectionStore';

type Message = { role: 'user' | 'assistant'; content: string };

const SYSTEM_VOICE = 'You are a helpful AI assistant. The user is walking outdoors with headphones. Keep every response to 2-3 sentences. Natural conversational tone, no markdown.';

export async function cloudChat(
  messages: Message[],
  mode: string,
  onChunk: (text: string) => void,
): Promise<string> {
  const { geminiKey, claudeKey } = useConnectionStore.getState();

  if (geminiKey) {
    try {
      return await _geminiChat(geminiKey, messages, onChunk);
    } catch (e) {
      console.warn('[cloudAI] Gemini failed:', e);
    }
  }

  if (claudeKey) {
    try {
      return await _claudeChat(claudeKey, messages, onChunk);
    } catch (e) {
      console.warn('[cloudAI] Claude failed:', e);
    }
  }

  throw new Error('No cloud API keys configured');
}

async function _geminiChat(
  apiKey: string,
  messages: Message[],
  onChunk: (text: string) => void,
): Promise<string> {
  const contents = messages.map((m) => ({
    role: m.role === 'assistant' ? 'model' : 'user',
    parts: [{ text: m.content }],
  }));

  const res = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:streamGenerateContent?key=${apiKey}&alt=sse`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        system_instruction: { parts: [{ text: SYSTEM_VOICE }] },
        contents,
        generationConfig: { maxOutputTokens: 256 },
      }),
    },
  );

  if (!res.ok) throw new Error(`Gemini ${res.status}`);

  const text = await res.text();
  let accumulated = '';

  for (const line of text.split('\n')) {
    if (!line.startsWith('data: ')) continue;
    try {
      const data = JSON.parse(line.slice(6));
      const chunk = data?.candidates?.[0]?.content?.parts?.[0]?.text ?? '';
      if (chunk) {
        accumulated += chunk;
        onChunk(accumulated);
      }
    } catch {}
  }

  return accumulated;
}

async function _claudeChat(
  apiKey: string,
  messages: Message[],
  onChunk: (text: string) => void,
): Promise<string> {
  const res = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-api-key': apiKey,
      'anthropic-version': '2023-06-01',
    },
    body: JSON.stringify({
      model: 'claude-haiku-4-5-20251001',
      max_tokens: 256,
      system: SYSTEM_VOICE,
      messages: messages.map((m) => ({ role: m.role, content: m.content })),
    }),
  });

  if (!res.ok) throw new Error(`Claude ${res.status}`);
  const data = await res.json();
  const text = data?.content?.[0]?.text ?? '';
  onChunk(text);
  return text;
}
