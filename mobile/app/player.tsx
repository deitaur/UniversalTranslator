/**
 * Main walking session screen — the "Spotify-like" player view.
 * Central animated orb changes state with the voice pipeline FSM.
 */
import React, { useCallback, useEffect, useRef } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet,
  Animated, StatusBar, Pressable,
} from 'react-native';
import { router } from 'expo-router';
import { useMachine } from '@xstate/react';
import { sessionMachine } from '@/state/sessionMachine';
import { useConnectionStore } from '@/state/connectionStore';
import { useProgressStore } from '@/state/progressStore';
import { C, MODE_COLORS, MODE_ICONS } from '@/theme';
import { ModeSelector } from '@/components/ModeSelector';
import { WalkTimer } from '@/components/WalkTimer';

export default function Player() {
  const [state, send] = useMachine(sessionMachine);
  const { pcUrl, currentMode, setCurrentMode } = useConnectionStore();
  const { addXp, incrementStreak } = useProgressStore();
  const pulseAnim = useRef(new Animated.Value(1)).current;
  const [showModes, setShowModes] = React.useState(false);

  const orbColor = MODE_COLORS[currentMode] ?? C.accent;
  const orbIcon  = MODE_ICONS[currentMode]  ?? '◉';

  // Pulse animation tied to FSM state
  useEffect(() => {
    const isListening = state.matches('LISTENING');
    const isSpeaking  = state.matches('SPEAKING');

    if (isListening) {
      Animated.loop(
        Animated.sequence([
          Animated.timing(pulseAnim, { toValue: 1.12, duration: 900, useNativeDriver: true }),
          Animated.timing(pulseAnim, { toValue: 1.0,  duration: 900, useNativeDriver: true }),
        ]),
      ).start();
    } else if (isSpeaking) {
      Animated.loop(
        Animated.sequence([
          Animated.timing(pulseAnim, { toValue: 1.2, duration: 200, useNativeDriver: true }),
          Animated.timing(pulseAnim, { toValue: 0.95, duration: 200, useNativeDriver: true }),
        ]),
      ).start();
    } else {
      pulseAnim.stopAnimation();
      Animated.timing(pulseAnim, { toValue: 1.0, duration: 300, useNativeDriver: true }).start();
    }
  }, [state.value, pulseAnim]);

  const handleOrbDoubleTap = useCallback(() => {
    send({ type: 'INTERRUPT' });
  }, [send]);

  function handleStop() {
    send({ type: 'SESSION_END' });
    router.replace('/summary');
  }

  const stateLabel: Record<string, string> = {
    IDLE:           'Tap to start',
    LISTENING:      'Listening…',
    PROCESSING_STT: 'Processing…',
    PROCESSING_LLM: 'Thinking…',
    SPEAKING:       'Speaking…',
    RECONNECTING:   'Reconnecting…',
    CLOUD_FALLBACK: 'Cloud mode',
  };

  return (
    <View style={styles.root}>
      <StatusBar barStyle="light-content" backgroundColor={C.bg} />

      {/* Top bar */}
      <View style={styles.topBar}>
        <TouchableOpacity onPress={() => setShowModes(true)}>
          <Text style={styles.menuIcon}>≡</Text>
        </TouchableOpacity>
        <WalkTimer running={!state.matches('IDLE')} />
      </View>

      {/* Orb */}
      <View style={styles.orbArea}>
        <Pressable onPress={handleOrbDoubleTap}>
          <Animated.View
            style={[
              styles.orb,
              { backgroundColor: orbColor + '22', borderColor: orbColor, transform: [{ scale: pulseAnim }] },
            ]}
          >
            <Text style={[styles.orbIcon, { color: orbColor }]}>{orbIcon}</Text>
            <Text style={[styles.orbLabel, { color: orbColor }]}>
              {stateLabel[String(state.value)] ?? ''}
            </Text>
          </Animated.View>
        </Pressable>
      </View>

      {/* Transcript */}
      {state.context?.transcript ? (
        <Text style={styles.transcript} numberOfLines={2}>
          "{state.context.transcript}"
        </Text>
      ) : null}

      {/* AI response streaming */}
      {state.context?.aiChunk ? (
        <View style={styles.responseBox}>
          <Text style={styles.responseText} numberOfLines={4}>
            {state.context.aiChunk}
          </Text>
        </View>
      ) : null}

      {/* Stop button */}
      <TouchableOpacity style={styles.stopBtn} onPress={handleStop}>
        <Text style={styles.stopText}>■  END SESSION</Text>
      </TouchableOpacity>

      {/* Mode selector bottom sheet */}
      {showModes && (
        <ModeSelector
          currentMode={currentMode}
          onSelect={(m) => { setCurrentMode(m); setShowModes(false); }}
          onClose={() => setShowModes(false)}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.bg, paddingHorizontal: 20 },
  topBar: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingTop: 52, marginBottom: 10 },
  menuIcon: { fontSize: 24, color: C.text },
  orbArea: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  orb: {
    width: 180,
    height: 180,
    borderRadius: 90,
    borderWidth: 2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  orbIcon:  { fontSize: 40, marginBottom: 6 },
  orbLabel: { fontSize: 13, fontWeight: '600', letterSpacing: 0.5 },
  transcript: {
    color: C.subtext,
    fontSize: 15,
    fontStyle: 'italic',
    textAlign: 'center',
    marginHorizontal: 16,
    marginBottom: 12,
  },
  responseBox: {
    backgroundColor: C.card,
    borderRadius: 12,
    padding: 14,
    marginBottom: 20,
    borderWidth: 1,
    borderColor: C.border,
  },
  responseText: { color: C.text, fontSize: 15, lineHeight: 22 },
  stopBtn: {
    backgroundColor: C.surface,
    borderRadius: 14,
    paddingVertical: 18,
    alignItems: 'center',
    marginBottom: 36,
    borderWidth: 1,
    borderColor: C.border,
  },
  stopText: { color: C.text, fontWeight: '700', fontSize: 15, letterSpacing: 1 },
});
