/**
 * Onboarding screen — connect to PC via QR scan or manual IP entry,
 * plus optional cloud API keys for fallback.
 */
import React, { useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  ScrollView, Alert, ActivityIndicator,
} from 'react-native';
import { router } from 'expo-router';
import { C } from '@/theme';
import { useConnectionStore } from '@/state/connectionStore';
import { testConnection } from '@/services/bridge';

export default function Onboarding() {
  const { setPcUrl, setGeminiKey, setClaudeKey, geminiKey, claudeKey } = useConnectionStore();
  const [ip, setIp] = useState('');
  const [port, setPort] = useState('8082');
  const [token, setToken] = useState('');
  const [testing, setTesting] = useState(false);
  const [status, setStatus] = useState<'idle' | 'ok' | 'fail'>('idle');

  async function handleTest() {
    const url = `ws://${ip.trim()}:${port.trim()}/?token=${token.trim()}`;
    setTesting(true);
    setStatus('idle');
    const ok = await testConnection(url);
    setTesting(false);
    setStatus(ok ? 'ok' : 'fail');
    if (ok) setPcUrl(url);
  }

  function handleStart() {
    if (status !== 'ok' && !geminiKey && !claudeKey) {
      Alert.alert(
        'No connection',
        'Either connect to your PC or add a cloud API key.',
      );
      return;
    }
    router.replace('/player');
  }

  return (
    <ScrollView style={styles.scroll} contentContainerStyle={styles.container}>
      <Text style={styles.logo}>◉  AI COMPANION</Text>
      <Text style={styles.subtitle}>Connect to your home PC</Text>

      {/* PC connection */}
      <View style={styles.card}>
        <Text style={styles.label}>IP Address</Text>
        <TextInput
          style={styles.input}
          placeholder="192.168.1.42"
          placeholderTextColor={C.muted}
          value={ip}
          onChangeText={setIp}
          keyboardType="numeric"
          autoCorrect={false}
        />
        <Text style={styles.label}>Port</Text>
        <TextInput
          style={styles.input}
          placeholder="8082"
          placeholderTextColor={C.muted}
          value={port}
          onChangeText={setPort}
          keyboardType="numeric"
        />
        <Text style={styles.label}>Token</Text>
        <TextInput
          style={styles.input}
          placeholder="Paste token from PC Settings"
          placeholderTextColor={C.muted}
          value={token}
          onChangeText={setToken}
          autoCorrect={false}
          secureTextEntry
        />
        <TouchableOpacity
          style={[styles.btn, styles.btnOutline]}
          onPress={handleTest}
          disabled={testing}
        >
          {testing
            ? <ActivityIndicator color={C.accent} />
            : <Text style={[styles.btnText, { color: C.accent }]}>
                {status === 'ok' ? '✓ Connected' : status === 'fail' ? '✗ Failed — retry' : 'Test Connection'}
              </Text>
          }
        </TouchableOpacity>
      </View>

      {/* Cloud fallback */}
      <View style={styles.card}>
        <Text style={styles.sectionTitle}>Cloud Fallback</Text>
        <Text style={styles.label}>Gemini API Key</Text>
        <TextInput
          style={styles.input}
          placeholder="AIza..."
          placeholderTextColor={C.muted}
          value={geminiKey}
          onChangeText={setGeminiKey}
          secureTextEntry
          autoCorrect={false}
        />
        <Text style={styles.label}>Claude API Key</Text>
        <TextInput
          style={styles.input}
          placeholder="sk-ant-..."
          placeholderTextColor={C.muted}
          value={claudeKey}
          onChangeText={setClaudeKey}
          secureTextEntry
          autoCorrect={false}
        />
      </View>

      <TouchableOpacity style={styles.btn} onPress={handleStart}>
        <Text style={styles.btnText}>Start  →</Text>
      </TouchableOpacity>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { flex: 1, backgroundColor: C.bg },
  container: { padding: 24, paddingBottom: 40 },
  logo: { fontSize: 26, fontWeight: '700', color: C.accent, textAlign: 'center', marginTop: 32 },
  subtitle: { color: C.muted, textAlign: 'center', marginTop: 6, marginBottom: 28, fontSize: 14 },
  card: {
    backgroundColor: C.card,
    borderRadius: 14,
    padding: 16,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: C.border,
  },
  sectionTitle: { color: C.text, fontWeight: '600', fontSize: 14, marginBottom: 10 },
  label: { color: C.subtext, fontSize: 12, marginBottom: 4, marginTop: 10 },
  input: {
    backgroundColor: C.cardAlt,
    color: C.text,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 14,
    borderWidth: 1,
    borderColor: C.border,
  },
  btn: {
    backgroundColor: C.accent,
    borderRadius: 12,
    paddingVertical: 16,
    alignItems: 'center',
    marginTop: 8,
  },
  btnOutline: {
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: C.accent,
    marginTop: 14,
  },
  btnText: { color: C.bg, fontWeight: '700', fontSize: 16 },
});
