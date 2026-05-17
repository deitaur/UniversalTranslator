/**
 * Zustand store — streaks, XP, and session history.
 * Persisted via Zustand persist + AsyncStorage.
 */
import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import AsyncStorage from '@react-native-async-storage/async-storage';

// XP formula: 50 base + minutes + streak multiplier
export function calcXp(durationSeconds: number, streak: number): number {
  const minutes    = durationSeconds / 60;
  const multiplier = 1.0 + streak * 0.05;
  return Math.round((50 + minutes) * multiplier);
}

export type SessionRecord = {
  id:              string;
  mode:            string;
  durationSeconds: number;
  xpGained:        number;
  date:            string;   // ISO
  topics?:         string[];
};

export type ProgressState = {
  streak:          number;
  totalXp:         number;
  lastSessionDate: string;
  sessions:        SessionRecord[];
  lastSession:     SessionRecord | null;

  addXp:           (amount: number) => void;
  incrementStreak: () => void;
  recordSession:   (s: Omit<SessionRecord, 'id'>) => void;
};

export const useProgressStore = create<ProgressState>()(
  persist(
    (set, get) => ({
      streak:          0,
      totalXp:         0,
      lastSessionDate: '',
      sessions:        [],
      lastSession:     null,

      addXp: (amount) =>
        set((s) => ({ totalXp: s.totalXp + amount })),

      incrementStreak: () => {
        const today     = new Date().toDateString();
        const yesterday = new Date(Date.now() - 86_400_000).toDateString();
        const last      = get().lastSessionDate;

        if (last === today) return;

        const newStreak = (last === yesterday || last === '')
          ? get().streak + 1
          : 1;

        set({ streak: newStreak, lastSessionDate: today });
      },

      recordSession: (s) => {
        const record: SessionRecord = { ...s, id: Date.now().toString() };
        set((state) => ({
          sessions:    [record, ...state.sessions].slice(0, 100),
          lastSession: record,
        }));
      },
    }),
    {
      name:    'progress-storage',
      storage: createJSONStorage(() => AsyncStorage),
      partialize: (s) => ({
        streak:          s.streak,
        totalXp:         s.totalXp,
        lastSessionDate: s.lastSessionDate,
        sessions:        s.sessions,
      }),
    },
  ),
);
