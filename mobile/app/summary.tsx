/**
 * Session summary screen — shown after a walking session ends.
 * Displays XP gained, streak, duration, and a shareable card.
 */
import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ScrollView, Share } from 'react-native';
import { router } from 'expo-router';
import { useProgressStore } from '@/state/progressStore';
import { useConnectionStore } from '@/state/connectionStore';
import { C, MODE_COLORS, MODE_ICONS } from '@/theme';

export default function Summary() {
  const { lastSession, streak, totalXp } = useProgressStore();
  const { currentMode } = useConnectionStore();

  const orbColor = MODE_COLORS[currentMode] ?? C.accent;
  const orbIcon  = MODE_ICONS[currentMode]  ?? '◉';
  const duration = lastSession?.durationSeconds
    ? formatDuration(lastSession.durationSeconds)
    : '—';
  const xpGained = lastSession?.xpGained ?? 0;

  async function handleShare() {
    try {
      await Share.share({
        message: `🔥 ${streak} day streak · +${xpGained} XP · ${duration} with AI Companion (${currentMode.replace('_', ' ')})`,
      });
    } catch {}
  }

  return (
    <ScrollView style={styles.scroll} contentContainerStyle={styles.container}>
      <Text style={styles.title}>Session Complete!</Text>

      {/* Mode badge */}
      <View style={[styles.modeBadge, { borderColor: orbColor }]}>
        <Text style={{ fontSize: 28 }}>{orbIcon}</Text>
        <View style={{ marginLeft: 12 }}>
          <Text style={[styles.modeName, { color: orbColor }]}>
            {currentMode.replace('_', ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
          </Text>
          <Text style={styles.modeMeta}>{duration}</Text>
        </View>
      </View>

      {/* Stats */}
      <View style={styles.statsRow}>
        <Stat emoji="🔥" label="Streak" value={`${streak} days`} />
        <Stat emoji="⚡" label="XP today" value={`+${xpGained}`} />
        <Stat emoji="🏆" label="Total XP" value={String(totalXp)} />
      </View>

      {/* Topics (placeholder — would be AI-generated summary) */}
      {lastSession?.topics && lastSession.topics.length > 0 && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Discussed</Text>
          {lastSession.topics.map((t, i) => (
            <Text key={i} style={styles.bullet}>• {t}</Text>
          ))}
        </View>
      )}

      {/* Action buttons */}
      <TouchableOpacity style={[styles.btn, styles.btnSecondary]} onPress={handleShare}>
        <Text style={[styles.btnText, { color: C.accent }]}>Share</Text>
      </TouchableOpacity>

      <TouchableOpacity style={styles.btn} onPress={() => router.replace('/player')}>
        <Text style={styles.btnText}>Another Walk</Text>
      </TouchableOpacity>

      <TouchableOpacity
        style={[styles.btn, { backgroundColor: C.surface, marginTop: 6 }]}
        onPress={() => router.replace('/')}
      >
        <Text style={[styles.btnText, { color: C.subtext }]}>Done</Text>
      </TouchableOpacity>
    </ScrollView>
  );
}

function Stat({ emoji, label, value }: { emoji: string; label: string; value: string }) {
  return (
    <View style={styles.stat}>
      <Text style={styles.statEmoji}>{emoji}</Text>
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

const styles = StyleSheet.create({
  scroll: { flex: 1, backgroundColor: C.bg },
  container: { padding: 24, paddingBottom: 48 },
  title: { fontSize: 26, fontWeight: '800', color: C.text, textAlign: 'center', marginTop: 32, marginBottom: 24 },
  modeBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: C.card,
    borderRadius: 14,
    padding: 16,
    borderWidth: 1,
    marginBottom: 20,
  },
  modeName: { fontSize: 17, fontWeight: '700' },
  modeMeta: { color: C.muted, marginTop: 2 },
  statsRow: { flexDirection: 'row', justifyContent: 'space-around', marginBottom: 20 },
  stat: { alignItems: 'center', flex: 1 },
  statEmoji: { fontSize: 24, marginBottom: 4 },
  statValue: { color: C.text, fontWeight: '700', fontSize: 18 },
  statLabel: { color: C.muted, fontSize: 11, marginTop: 2 },
  card: {
    backgroundColor: C.card,
    borderRadius: 12,
    padding: 14,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: C.border,
  },
  cardTitle: { color: C.subtext, fontWeight: '600', marginBottom: 8 },
  bullet: { color: C.text, marginVertical: 3, paddingLeft: 4 },
  btn: {
    backgroundColor: C.accent,
    borderRadius: 14,
    paddingVertical: 16,
    alignItems: 'center',
    marginBottom: 10,
  },
  btnSecondary: { backgroundColor: 'transparent', borderWidth: 1, borderColor: C.accent },
  btnText: { color: C.bg, fontWeight: '700', fontSize: 16 },
});
