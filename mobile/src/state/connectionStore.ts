/**
 * Zustand store — persisted connection settings and current mode.
 * Uses AsyncStorage via Zustand persist middleware (works in Expo Go).
 */
import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import AsyncStorage from '@react-native-async-storage/async-storage';

export type ConnectionState = {
  pcUrl:          string;
  geminiKey:      string;
  claudeKey:      string;
  currentMode:    string;
  connected:      boolean;

  setPcUrl:       (url: string)  => void;
  setGeminiKey:   (key: string)  => void;
  setClaudeKey:   (key: string)  => void;
  setCurrentMode: (mode: string) => void;
  setConnected:   (v: boolean)   => void;
};

export const useConnectionStore = create<ConnectionState>()(
  persist(
    (set) => ({
      pcUrl:          '',
      geminiKey:      '',
      claudeKey:      '',
      currentMode:    'negotiator',
      connected:      false,

      setPcUrl:       (url)  => set({ pcUrl: url }),
      setGeminiKey:   (key)  => set({ geminiKey: key }),
      setClaudeKey:   (key)  => set({ claudeKey: key }),
      setCurrentMode: (mode) => set({ currentMode: mode }),
      setConnected:   (v)    => set({ connected: v }),
    }),
    {
      name:    'connection-storage',
      storage: createJSONStorage(() => AsyncStorage),
      // Don't persist transient state
      partialize: (s) => ({
        pcUrl:       s.pcUrl,
        geminiKey:   s.geminiKey,
        claudeKey:   s.claudeKey,
        currentMode: s.currentMode,
      }),
    },
  ),
);
