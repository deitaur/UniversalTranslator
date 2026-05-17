/**
 * Mic capture + audio playback pipeline.
 *
 * Recording:  expo-av Audio.Recording → PCM 16kHz mono int16 chunks → bridge
 * Playback:   base64 MP3 chunks from bridge → concat → expo-av Audio.Sound
 */
import { Audio } from 'expo-av';
import { sendAudioChunk, sendAudioEnd } from './bridge';

let _recording: Audio.Recording | null = null;
const _playbackChunks: string[] = [];   // base64 MP3 chunks
let _playbackSound: Audio.Sound | null = null;

// ── Recording ─────────────────────────────────────────────────────────────────

export async function startRecording(): Promise<void> {
  await Audio.requestPermissionsAsync();
  await Audio.setAudioModeAsync({
    allowsRecordingIOS: true,
    playsInSilentModeIOS: true,
  });

  _recording = new Audio.Recording();
  await _recording.prepareToRecordAsync({
    android: {
      extension:            '.wav',
      outputFormat:         Audio.AndroidOutputFormat.DEFAULT,
      audioEncoder:         Audio.AndroidAudioEncoder.DEFAULT,
      sampleRate:           16000,
      numberOfChannels:     1,
      bitRate:              128000,
    },
    ios: {
      extension:            '.wav',
      audioQuality:         Audio.IOSAudioQuality.HIGH,
      sampleRate:           16000,
      numberOfChannels:     1,
      bitRate:              128000,
      linearPCMBitDepth:    16,
      linearPCMIsBigEndian: false,
      linearPCMIsFloat:     false,
    },
    web: {},
  });

  await _recording.startAsync();
}

export async function stopRecordingAndSend(): Promise<void> {
  if (!_recording) return;
  await _recording.stopAndUnloadAsync();
  const uri = _recording.getURI();
  _recording = null;

  if (!uri) { sendAudioEnd(); return; }

  // Read file as base64 and send in one chunk (for simplicity)
  // In production, stream 50 ms chunks while recording
  const response = await fetch(uri);
  const blob     = await response.blob();
  const reader   = new FileReader();
  reader.onloadend = () => {
    const base64 = (reader.result as string).split(',')[1] ?? '';
    sendAudioChunk(base64);
    sendAudioEnd();
  };
  reader.readAsDataURL(blob);
}

// ── Playback ──────────────────────────────────────────────────────────────────

export function queueAudioChunk(base64Mp3: string): void {
  _playbackChunks.push(base64Mp3);
}

export async function flushAndPlay(): Promise<void> {
  if (!_playbackChunks.length) return;

  // Concatenate all received MP3 chunks into a data URI
  const combined = _playbackChunks.join('');
  _playbackChunks.length = 0;

  const dataUri = `data:audio/mp3;base64,${combined}`;

  if (_playbackSound) {
    await _playbackSound.unloadAsync();
    _playbackSound = null;
  }

  const { sound } = await Audio.Sound.createAsync({ uri: dataUri }, { shouldPlay: true });
  _playbackSound = sound;
}

export async function stopPlayback(): Promise<void> {
  if (_playbackSound) {
    await _playbackSound.stopAsync();
    await _playbackSound.unloadAsync();
    _playbackSound = null;
  }
  _playbackChunks.length = 0;
}
