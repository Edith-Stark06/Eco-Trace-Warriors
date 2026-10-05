import React, { useEffect, useState } from 'react';
import { ScrollView, StyleSheet, Text, View, Pressable } from 'react-native';
import QRCode from 'react-native-qrcode-svg';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { deviceAiApi } from '../api/deviceAiApi';
import { submissionsApi } from '../api/submissionsApi';
import { syncQueueStorage } from '../storage/syncQueue';
import { useNetworkStatus } from '../hooks/useNetworkStatus';
import { ApiError } from '../api/ApiError';
import { LoadingIndicator } from '../components/LoadingIndicator';
import { ErrorState } from '../components/ErrorState';
import { Card } from '../components/common/Card';
import { theme } from '../theme';
import type { DeviceRecord } from '../types/device';
import { buildEcoTraceQrPayload, getEcoId } from '../lib/ecoQrPayload';

type Props = NativeStackScreenProps<RootStackParamList, 'RegisterDevice'>;

type Phase = 'classifying' | 'confirming' | 'done' | 'error';

/**
 * Runs the captured images through the real AI candidate-registration
 * pipeline (POST /devices/register), shows the resulting classification,
 * then confirms + finalizes the AI-side device record.
 */
export function RegisterDeviceScreen({ route, navigation }: Props) {
  const { images, submissionId } = route.params;
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
        try {
          await deviceAiApi.enrich(device.device_id);
          await deviceAiApi.anchorPassport(device.device_id);
        } catch {
          // Best-effort
        }
        if (submissionId) {
          try {
            await submissionsApi.linkDevice(submissionId, { deviceId: device.device_id });
          } catch {
            // Best-effort
          }
        }
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
    // The EcoID the backend already assigned at registration time — never
    // generated locally. QR display is a best-effort handoff UI only: if
    // it's absent for any reason, registration itself has already succeeded
    // and is not affected.
    const ecoId = device ? getEcoId(device) : null;

    return (
      <View style={styles.doneContainer}>
        <Card variant="elevated" style={styles.doneCard}>
          <View style={styles.doneIconContainer}>
            <Text style={styles.doneIcon}>✓</Text>
          </View>
          <Text style={styles.title}>Device recorded</Text>
          <Text style={styles.body}>
            {isOnline
              ? 'The device has been confirmed and finalized in the device intelligence record.'
              : 'You are offline — the device confirmation is queued and will finalize automatically once you reconnect.'}
          </Text>

          {ecoId ? (
            <View style={styles.qrBlock} testID="ecoid-qr-block">
              <View style={styles.qrFrame}>
                <QRCode
                  value={buildEcoTraceQrPayload(ecoId)}
                  size={200}
                  ecl="M"
                  backgroundColor="#FFFFFF"
                  color="#000000"
                />
              </View>
              <Text style={styles.ecoIdLabel}>EcoID</Text>
              <Text style={styles.ecoIdValue} testID="ecoid-value">
                {ecoId}
              </Text>
              {device ? (
                <View style={styles.deviceMetaRow}>
                  <Text style={styles.deviceMetaType}>{device.device_type}</Text>
                  <Text style={styles.deviceMetaConfidence}>
                    {(device.confidence * 100).toFixed(0)}% confidence
                  </Text>
                </View>
              ) : null}
              <Text style={styles.qrHint}>Show this QR to the consumer to verify the device.</Text>
            </View>
          ) : null}

          <Pressable
            style={styles.doneButton}
            accessibilityRole="button"
            onPress={() => navigation.navigate('Dashboard')}
          >
            <Text style={styles.doneButtonText}>Done</Text>
          </Pressable>
        </Card>
      </View>
    );
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <View style={styles.header}>
        <View style={styles.aiTag}>
          <Text style={styles.aiTagText}>YOLO11 DETECTOR INFERENCE</Text>
        </View>
        <Text style={styles.title}>Device detected</Text>
        <Text style={styles.subtitle}>
          Review the detected electronic hardware classification before committing to identity record.
        </Text>
      </View>

      {device ? (
        <Card variant="elevated" style={styles.resultCard}>
          <View style={styles.resultTop}>
            <View style={styles.typeBadge}>
              <Text style={styles.typeIcon}>📱</Text>
              <Text style={styles.typeName}>{device.device_type}</Text>
            </View>
            <View style={styles.confidencePill}>
              <Text style={styles.confidenceText}>
                {(device.confidence * 100).toFixed(0)}% Match
              </Text>
            </View>
          </View>

          <View style={styles.divider} />

          <View style={styles.detailsTable}>
            <Row label="Type" value={device.device_type} />
            <Row
              label="Confidence"
              value={`${(device.confidence * 100).toFixed(0)}% (${device.confidence_state})`}
            />
            <Row label="Lifecycle state" value={device.registration_state} />
            <Row label="Model version" value={device.model_version} isMono />
            {device.device_id ? (
              <Row label="Device ID" value={device.device_id} isMono />
            ) : null}
          </View>
        </Card>
      ) : (
        <Card variant="outlined" style={styles.resultCard}>
          <Text style={styles.body}>No device was detected in the captured images.</Text>
        </Card>
      )}

      {/* Primary Confirm Button with testID */}
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

function Row({ label, value, isMono }: { label: string; value: string; isMono?: boolean }) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>{label}</Text>
      <Text style={[styles.rowValue, isMono && styles.rowValueMono]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.colors.background.app,
  },
  content: {
    padding: theme.spacing.lg,
    paddingBottom: theme.spacing.xxl,
  },
  header: {
    marginBottom: theme.spacing.md,
    paddingBottom: theme.spacing.base,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.slate[100],
  },
  aiTag: {
    alignSelf: 'flex-start',
    backgroundColor: theme.colors.forest[100],
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: 3,
    borderRadius: theme.radius.sm,
    marginBottom: 6,
  },
  aiTagText: {
    color: theme.colors.forest[800],
    fontSize: 10,
    fontWeight: theme.typography.weight.bold,
    letterSpacing: 0.8,
  },
  title: {
    fontSize: theme.typography.size.xl,
    fontWeight: theme.typography.weight.bold,
    color: theme.colors.slate[900],
  },
  subtitle: {
    fontSize: theme.typography.size.xs,
    color: theme.colors.slate[500],
    marginTop: 4,
    lineHeight: 18,
  },
  resultCard: {
    padding: theme.spacing.lg,
    marginBottom: theme.spacing.xl,
  },
  resultTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: theme.spacing.md,
  },
  typeBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  typeIcon: {
    fontSize: 22,
  },
  typeName: {
    fontSize: theme.typography.size.base,
    fontWeight: theme.typography.weight.bold,
    color: theme.colors.slate[900],
    textTransform: 'capitalize',
  },
  confidencePill: {
    backgroundColor: theme.colors.emerald[100],
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: 4,
    borderRadius: theme.radius.full,
  },
  confidenceText: {
    fontSize: 11,
    fontWeight: theme.typography.weight.bold,
    color: theme.colors.emerald[800],
  },
  divider: {
    height: 1,
    backgroundColor: theme.colors.slate[100],
    marginBottom: theme.spacing.sm,
  },
  detailsTable: {
    gap: 6,
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 4,
    alignItems: 'center',
  },
  rowLabel: {
    color: theme.colors.slate[500],
    fontSize: theme.typography.size.xs,
  },
  rowValue: {
    color: theme.colors.slate[900],
    fontSize: theme.typography.size.xs,
    fontWeight: theme.typography.weight.semibold,
  },
  rowValueMono: {
    fontFamily: 'monospace',
    color: theme.colors.forest[800],
  },
  confirmButton: {
    backgroundColor: theme.colors.forest[700],
    color: '#FFFFFF',
    textAlign: 'center',
    paddingVertical: 14,
    borderRadius: theme.radius.md,
    fontWeight: theme.typography.weight.bold,
    fontSize: theme.typography.size.sm,
    overflow: 'hidden',
    minHeight: 48,
    ...theme.elevation.xs,
  },
  body: {
    fontSize: theme.typography.size.xs,
    color: theme.colors.slate[600],
    lineHeight: 20,
    marginTop: theme.spacing.sm,
    marginBottom: theme.spacing.lg,
    textAlign: 'center',
  },
  doneContainer: {
    flex: 1,
    backgroundColor: theme.colors.background.app,
    justifyContent: 'center',
    padding: theme.spacing.xl,
  },
  doneCard: {
    alignItems: 'center',
    padding: theme.spacing.xl,
  },
  doneIconContainer: {
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: theme.colors.forest[100],
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: theme.spacing.md,
  },
  doneIcon: {
    fontSize: 28,
    color: theme.colors.forest[700],
    fontWeight: theme.typography.weight.bold,
  },
  qrBlock: {
    alignItems: 'center',
    marginBottom: theme.spacing.lg,
  },
  qrFrame: {
    backgroundColor: '#FFFFFF',
    padding: theme.spacing.md,
    borderRadius: theme.radius.md,
    borderWidth: 1,
    borderColor: theme.colors.slate[100],
    marginBottom: theme.spacing.md,
    ...theme.elevation.xs,
  },
  ecoIdLabel: {
    fontSize: theme.typography.size.xs,
    fontWeight: theme.typography.weight.bold,
    color: theme.colors.slate[500],
    letterSpacing: 1.2,
    textTransform: 'uppercase',
  },
  ecoIdValue: {
    fontSize: theme.typography.size.xl,
    fontWeight: theme.typography.weight.bold,
    color: theme.colors.slate[900],
    marginTop: 2,
    fontFamily: 'monospace',
  },
  deviceMetaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: theme.spacing.sm,
  },
  deviceMetaType: {
    fontSize: theme.typography.size.sm,
    fontWeight: theme.typography.weight.semibold,
    color: theme.colors.forest[800],
    textTransform: 'capitalize',
  },
  deviceMetaConfidence: {
    fontSize: theme.typography.size.xs,
    color: theme.colors.slate[500],
  },
  qrHint: {
    fontSize: theme.typography.size.xs,
    color: theme.colors.slate[500],
    textAlign: 'center',
    marginTop: theme.spacing.md,
    paddingHorizontal: theme.spacing.md,
  },
  doneButton: {
    backgroundColor: theme.colors.forest[700],
    borderRadius: theme.radius.md,
    paddingVertical: 12,
    paddingHorizontal: theme.spacing.xl,
    alignItems: 'center',
    minHeight: 44,
  },
  doneButtonText: {
    color: '#FFFFFF',
    fontSize: theme.typography.size.xs,
    fontWeight: theme.typography.weight.bold,
  },
});
