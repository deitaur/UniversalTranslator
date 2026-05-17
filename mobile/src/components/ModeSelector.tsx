/**
 * Bottom-sheet mode selector — swipe up from the player screen.
 * Shows builtin modes with streak counters.
 */
import React from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, Modal, Pressable, ScrollView,
} from 'react-native';
import { C, MODE_COLORS, MODE_ICONS } from '@/theme';
import { useProgressStore } from '@/state/progressStore';

const BUILTIN_MODES = [
  { id: 'health_coach',   name: 'Health Coach' },
  { id: 'psychologist',   name: 'Psychologist' },
  { id: 'language_tutor', name: 'Lang Tutor' },
  { id: 'topic_learning', name: 'Topic Learn' },
  { id: 'negotiator',     name: 'Negotiator' },
  { id: 'teacher',        name: 'Eng Teacher' },
];

type Props = {
  currentMode: string;
  onSelect:    (mode: string) => void;
  onClose:     () => void;
};

export function ModeSelector({ currentMode, onSelect, onClose }: Props) {
  const { sessions } = useProgressStore();

  function streakFor(modeId: string): number {
    const modeSessions = sessions.filter((s) => s.mode === modeId);
    if (!modeSessions.length) return 0;

    let streak = 0;
    const today = new Date();
    for (let i = 0; i < 365; i++) {
      const d = new Date(today);
      d.setDate(today.getDate() - i);
      const dateStr = d.toDateString();
      if (modeSessions.some((s) => new Date(s.date).toDateString() === dateStr)) {
        streak++;
      } else {
        break;
      }
    }
    return streak;
  }

  return (
    <Modal transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={styles.backdrop} onPress={onClose} />
      <View style={styles.sheet}>
        <View style={styles.handle} />
        <Text style={styles.title}>Choose walking mode</Text>
        <ScrollView contentContainerStyle={styles.grid}>
          {BUILTIN_MODES.map((m) => {
            const color  = MODE_COLORS[m.id] ?? C.accent;
            const icon   = MODE_ICONS[m.id]  ?? '◉';
            const streak = streakFor(m.id);
            const active = m.id === currentMode;
            return (
              <TouchableOpacity
                key={m.id}
                style={[styles.tile, active && { borderColor: color, borderWidth: 2 }]}
                onPress={() => onSelect(m.id)}
              >
                <Text style={styles.tileIcon}>{icon}</Text>
                <Text style={[styles.tileName, { color: active ? color : C.text }]}>{m.name}</Text>
                {streak > 0 && (
                  <Text style={[styles.tileStreak, { color }]}>🔥 {streak}d</Text>
                )}
              </TouchableOpacity>
            );
          })}
        </ScrollView>
      </View>
    </Modal>
  );
}

const TILE_W = 150;

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: '#00000066' },
  sheet: {
    backgroundColor: C.card,
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    padding: 20,
    paddingBottom: 40,
    borderWidth: 1,
    borderColor: C.border,
  },
  handle: {
    width: 40, height: 4,
    backgroundColor: C.border,
    borderRadius: 2,
    alignSelf: 'center',
    marginBottom: 16,
  },
  title: { color: C.text, fontWeight: '700', fontSize: 17, marginBottom: 16, textAlign: 'center' },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 12, justifyContent: 'center' },
  tile: {
    width: TILE_W,
    backgroundColor: C.surface,
    borderRadius: 14,
    padding: 16,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: C.border,
  },
  tileIcon:   { fontSize: 30, marginBottom: 8 },
  tileName:   { fontWeight: '600', fontSize: 13, textAlign: 'center' },
  tileStreak: { fontSize: 11, marginTop: 6 },
});
