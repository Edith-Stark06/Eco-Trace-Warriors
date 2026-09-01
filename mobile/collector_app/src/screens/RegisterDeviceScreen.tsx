import React, { useEffect, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { deviceAiApi } from '../api/deviceAiApi';
import { syncQueueStorage } from '../storage/syncQueue';
import { useNetworkStatus } from '../hooks/useNetworkStatus';
import { ApiError } from '../api/ApiError';
import { LoadingIndicator } from '../components/LoadingIndicator';
import { ErrorState } from '../components/ErrorState';
import type { DeviceRecord } from '../types/device';

type Props = NativeStackScreenProps<RootStackParamList, 'RegisterDevice'>;

type Phase = 'classifying' | 'confirming' | 'done' | 'error';

/**
 * Runs the captured images through the real AI candidate-registration
 * pipeline (POST /devices/register), shows the resulting classification,
 * then confirms + finalizes the AI-side device record
 * (intelligence/device_ai — a separate system from the backend's
 * Submission model, see docs/engineering/03_ARCHITECTURE.md).
 *
 * This screen intentionally does NOT create a backend Submission:
 * POST /submissions requires the CONSUMER role
 * (backend/src/modules/submission/submission.routes.ts) — a Collector's
 * real authorized actions are accept/start/complete on a Submission a
 * Consumer already created and an Admin/Government already assigned to
 * them (see SubmissionDetailScreen). This screen instead documents the
 * physical device intelligence-side for the pickup already in hand.
 */
export function RegisterDeviceScreen({ route, navigation }: Props) {
  const { images } = route.params;
  const isOnline = useNetworkStatus();
  const [phase, setPhase] = useState<Phase>('classifying');
  const [device, setDevice] = useState<DeviceRecord | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const result = await deviceAiApi.registerDevices(images);
        if (cancelled) return;
        const first = result.devices[0] ?? null;
        setDevice(first);
        setPhase('confirming');
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : 'Device classification failed.');
        setPhase('error');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [images]);

  const handleConfirm = async () => {
    if (!device) return;
    try {
      await deviceAiApi.confirm(device.device_id);
      if (isOnline) {
        await deviceAiApi.finalize(device.device_id);
      } else {
        await syncQueueStorage.enqueue(device.device_id, device.device_type);
      }
      setPhase('done');
    } catch (err) {
      if (err instanceof ApiError && err.isNetworkError) {
        await syncQueueStorage.enqueue(device.device_id, device.device_type);
        setPhase('done');
        return;
      }
      setError(err instanceof ApiError ? err.message : 'Unable to confirm the device.');
      setPhase('error');
    }
  };

  if (phase === 'classifying') {
    return <LoadingIndicator label="Classifying device…" />;
  }

  if (phase === 'error') {
    return <ErrorState message={error ?? 'Something went wrong.'} onRetry={() => navigation.goBack()} />;
  }

  if (phase === 'done') {
    return (
      <View style={styles.container}>
        <Text style={styles.title}>Device recorded</Text>
        <Text style={styles.body}>
          {isOnline
            ? 'The device has been confirmed and finalized in the device intelligence record.'
            : 'You are offline — the device confirmation is queued and will finalize automatically once you reconnect.'}
        </Text>
        <Text
          style={styles.link}
          accessibilityRole="button"
          onPress={() => navigation.navigate('Dashboard')}
        >
          Back to dashboard
        </Text>
      </View>
    );
  }

  return (
    <ScrollView style={styles.container}>
      <Text style={styles.title}>Device detected</Text>
      {device ? (
        <View style={styles.card}>
          <Row label="Type" value={device.device_type} />
          <Row label="Confidence" value={`${(device.confidence * 100).toFixed(0)}% (${device.confidence_state})`} />
          <Row label="Lifecycle state" value={device.registration_state} />
          <Row label="Model version" value={device.model_version} />
        </View>
      ) : (
        <Text style={styles.body}>No device was detected in the captured images.</Text>
      )}
      <Text
        style={styles.confirmButton}
        accessibilityRole="button"
        accessibilityLabel="Confirm device"
        onPress={handleConfirm}
        testID="register-confirm-button"
      >
        Confirm device
      </Text>
    </ScrollView>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>{label}</Text>
      <Text style={styles.rowValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#FFFFFF', padding: 16 },
  title: { fontSize: 20, fontWeight: '700', color: '#1B5E20', marginBottom: 16 },
  body: { fontSize: 14, color: '#4B5563', marginBottom: 16 },
  card: { borderWidth: 1, borderColor: '#E5E7EB', borderRadius: 8, padding: 12, marginBottom: 24 },
  row: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 6 },
  rowLabel: { color: '#6B7280', fontSize: 13 },
  rowValue: { color: '#111827', fontSize: 13, fontWeight: '600' },
  link: { color: '#2E7D32', fontWeight: '600', marginTop: 16 },
  confirmButton: {
    backgroundColor: '#2E7D32',
    color: '#FFFFFF',
    textAlign: 'center',
    paddingVertical: 14,
    borderRadius: 8,
    fontWeight: '600',
    overflow: 'hidden',
    minHeight: 44,
  },
});
