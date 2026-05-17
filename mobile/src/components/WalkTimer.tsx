import React, { useEffect, useRef, useState } from 'react';
import { Text, StyleSheet } from 'react-native';
import { C } from '@/theme';

type Props = { running: boolean };

export function WalkTimer({ running }: Props) {
  const [seconds, setSeconds] = useState(0);
  const interval = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (running) {
      interval.current = setInterval(() => setSeconds((s) => s + 1), 1000);
    } else {
      if (interval.current) clearInterval(interval.current);
    }
    return () => { if (interval.current) clearInterval(interval.current); };
  }, [running]);

  const m = Math.floor(seconds / 60).toString().padStart(2, '0');
  const s = (seconds % 60).toString().padStart(2, '0');

  return <Text style={styles.timer}>⏱ {m}:{s}</Text>;
}

const styles = StyleSheet.create({
  timer: { color: C.muted, fontSize: 14, fontVariant: ['tabular-nums'] },
});
