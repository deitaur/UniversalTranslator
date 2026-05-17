/**
 * XState v5 FSM — voice session flow.
 *
 * States:
 *   IDLE → LISTENING → PROCESSING_STT → PROCESSING_LLM →
 *   SPEAKING → LISTENING (loop)
 *
 * Events from the bridge WebSocket update the state.
 * INTERRUPT and SESSION_END are user-triggered.
 */
import { setup, assign } from 'xstate';

export type SessionContext = {
  transcript:  string;
  aiChunk:     string;
  sessionId:   string;
  error:       string;
};

export type SessionEvent =
  | { type: 'START';         mode: string; lang: string }
  | { type: 'AUDIO_END' }
  | { type: 'TRANSCRIPT';    text: string }
  | { type: 'LLM_CHUNK';     text: string; done: boolean }
  | { type: 'AUDIO_CHUNK' }
  | { type: 'AUDIO_END_TTS' }
  | { type: 'INTERRUPT' }
  | { type: 'SESSION_END' }
  | { type: 'STATE';         state: 'listening' | 'thinking' | 'speaking' }
  | { type: 'SESSION_ACK';   sessionId: string }
  | { type: 'ERROR';         message: string }
  | { type: 'RECONNECTING' }
  | { type: 'CLOUD_FALLBACK' };

export const sessionMachine = setup({
  types: {
    context: {} as SessionContext,
    events:  {} as SessionEvent,
  },
}).createMachine({
  id: 'session',
  initial: 'IDLE',
  context: {
    transcript: '',
    aiChunk:    '',
    sessionId:  '',
    error:      '',
  },
  states: {
    IDLE: {
      on: {
        START: 'LISTENING',
        SESSION_ACK: {
          actions: assign({ sessionId: ({ event }) => event.sessionId }),
        },
      },
    },

    LISTENING: {
      on: {
        AUDIO_END:     'PROCESSING_STT',
        INTERRUPT:     'LISTENING',
        SESSION_END:   'IDLE',
        STATE: {
          guard: ({ event }) => event.state === 'listening',
        },
      },
    },

    PROCESSING_STT: {
      on: {
        TRANSCRIPT: {
          target:  'PROCESSING_LLM',
          actions: assign({ transcript: ({ event }) => event.text }),
        },
        STATE: [
          { guard: ({ event }) => event.state === 'listening', target: 'LISTENING' },
        ],
        INTERRUPT:   'LISTENING',
        SESSION_END: 'IDLE',
      },
    },

    PROCESSING_LLM: {
      entry: assign({ aiChunk: '' }),
      on: {
        LLM_CHUNK: {
          actions: assign({ aiChunk: ({ event }) => event.text }),
        },
        STATE: [
          { guard: ({ event }) => event.state === 'speaking',  target: 'SPEAKING' },
          { guard: ({ event }) => event.state === 'listening', target: 'LISTENING' },
        ],
        INTERRUPT:   'LISTENING',
        SESSION_END: 'IDLE',
      },
    },

    SPEAKING: {
      on: {
        AUDIO_END_TTS: 'LISTENING',
        STATE: [
          { guard: ({ event }) => event.state === 'listening', target: 'LISTENING' },
        ],
        INTERRUPT:   'LISTENING',
        SESSION_END: 'IDLE',
      },
    },

    RECONNECTING: {
      after: { 5000: 'CLOUD_FALLBACK' },
      on: {
        STATE:       'LISTENING',
        SESSION_END: 'IDLE',
      },
    },

    CLOUD_FALLBACK: {
      on: {
        STATE:       'LISTENING',
        SESSION_END: 'IDLE',
      },
    },
  },
});
