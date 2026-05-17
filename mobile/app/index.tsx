/**
 * Entry point — routes to onboarding if PC address not configured,
 * otherwise to the player screen.
 * Waits for Zustand AsyncStorage hydration before redirecting.
 */
import { useEffect, useState } from 'react';
import { View, ActivityIndicator } from 'react-native';
import { Redirect } from 'expo-router';
import { useConnectionStore } from '@/state/connectionStore';
import { C } from '@/theme';

export default function Index() {
  const [ready, setReady] = useState(false);
  const pcUrl = useConnectionStore((s) => s.pcUrl);

  useEffect(() => {
    // Give Zustand persist a tick to rehydrate from AsyncStorage
    const t = setTimeout(() => setReady(true), 50);
    return () => clearTimeout(t);
  }, []);

  if (!ready) {
    return (
      <View style={{ flex: 1, backgroundColor: C.bg, justifyContent: 'center', alignItems: 'center' }}>
        <ActivityIndicator color={C.accent} />
      </View>
    );
  }

  return <Redirect href={pcUrl ? '/player' : '/onboarding'} />;
}
