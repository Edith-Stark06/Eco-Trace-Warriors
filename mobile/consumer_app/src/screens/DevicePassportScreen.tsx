import React, { useCallback, useEffect, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { deviceAiApi } from '../api/deviceAiApi';
import { ApiError } from '../api/ApiError';
import { LoadingIndicator } from '../components/LoadingIndicator';
import { ErrorState } from '../components/ErrorState';
import type { DevicePassportPayload, TrustStatusPayload } from '../types/device';
import type { PassportVerification } from '../types/verification';

type Props = NativeStackScreenProps<RootStackParamList, 'DevicePassport'>;

const TRUST_LABEL: Record<string, string> = {
  UNANCHORED: 'Not yet anchored to blockchain',
  ANCHORED: 'Anchored to blockchain',
  VERIFIED: 'Verified on blockchain',
  MISMATCH: 'Blockchain mismatch detected',
  STALE: 'Blockchain anchor is stale',
};

/**
 * Device passport + trust + blockchain verification — reads exclusively
 * through device_ai's REST API (which owns the real FabricGatewayClient,
 * P9.2); this app never touches a Fabric peer, wallet, or private key
 * directly (P9.6 architecture rule).
 */
export function DevicePassportScreen({ route, navigation }: Props) {
  const { deviceId } = route.params;
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [error, setError] = useState<string | null>(null);
  const [passport, setPassport] = useState<DevicePassportPayload | null>(null);
  const [trust, setTrust] = useState<TrustStatusPayload | null>(null);
  const [verification, setVerification] = useState<PassportVerification | null>(null);

  const load = useCallback(async () => {
    setStatus('loading');
    try {
      const [passportRes, trustRes, verifyRes] = await Promise.all([
        deviceAiApi.getPassport(deviceId),
        deviceAiApi.getTrustStatus(deviceId),
        deviceAiApi.verifyPassport(deviceId).catch(() => null),
      ]);
      setPassport(passportRes.passport);
      setTrust(trustRes.trust);
      setVerification(verifyRes?.verification ?? null);
      setStatus('ready');
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 404
          ? 'No device was found for this code.'
          : err instanceof ApiError
            ? err.message
            : 'Unable to load this device.',
      );
      setStatus('error');
    }
  }, [deviceId]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      deviceAiApi.getPassport(deviceId),
      deviceAiApi.getTrustStatus(deviceId),
      deviceAiApi.verifyPassport(deviceId).catch(() => null),
    ])
      .then(([passportRes, trustRes, verifyRes]) => {
        if (cancelled) return;
        setPassport(passportRes.passport);
        setTrust(trustRes.trust);
        setVerification(verifyRes?.verification ?? null);
        setStatus('ready');
      })
      .catch((err) => {
        if (cancelled) return;
        setError(
          err instanceof ApiError && err.status === 404
            ? 'No device was found for this code.'
            : err instanceof ApiError
              ? err.message
              : 'Unable to load this device.',
        );
        setStatus('error');
      });
    return () => {
      cancelled = true;
    };
  }, [deviceId]);

  if (status === 'loading') return <LoadingIndicator label="Loading device passport…" />;
  if (status === 'error' || !passport || !trust) {
    return <ErrorState message={error ?? 'Device not found.'} onRetry={load} />;
  }

  return (
    <ScrollView style={styles.container}>
      <Text style={styles.title}>{passport.device_id}</Text>
      {passport.eco_id ? <Text style={styles.subtitle}>{passport.eco_id}</Text> : null}

      <View style={[styles.trustBadge, trust.status === 'VERIFIED' && styles.trustBadgeVerified, trust.status === 'MISMATCH' && styles.trustBadgeError]}>
        <Text style={styles.trustBadgeText} accessibilityRole="text">
          {TRUST_LABEL[trust.status] ?? trust.status}
        </Text>
      </View>

      <Section title="Lifecycle">
        <Row label="State" value={String(passport.lifecycle?.state ?? 'Unknown')} />
        <Row label="Generated" value={new Date(passport.generated_at).toLocaleString()} />
      </Section>

      <Section title="Trust & blockchain anchor">
        <Row label="Trust status" value={trust.status} />
        <Row label="Anchor ID" value={trust.anchor_id ?? 'Not anchored'} />
        <Row label="Fresh" value={trust.is_fresh ? 'Yes' : 'No'} />
        <Row label="Reason" value={trust.reason} />
      </Section>

      {verification ? (
        <Section title="Passport verification">
          <Row label="Status" value={verification.verification_status} />
          <Row label="Verified at" value={new Date(verification.verified_at).toLocaleString()} />
          {verification.warnings.length > 0 ? (
            <Text style={styles.warning}>{verification.warnings.join('; ')}</Text>
          ) : null}
          {verification.errors.length > 0 ? (
            <Text style={styles.errorText} accessibilityRole="alert">
              {verification.errors.join('; ')}
            </Text>
          ) : null}
        </Section>
      ) : null}
    </ScrollView>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {children}
    </View>
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
  title: { fontSize: 18, fontWeight: '700', color: '#111827' },
  subtitle: { fontSize: 13, color: '#6B7280', marginTop: 2 },
  trustBadge: { alignSelf: 'flex-start', backgroundColor: '#FEF3C7', borderRadius: 8, paddingHorizontal: 12, paddingVertical: 6, marginTop: 12, marginBottom: 8 },
  trustBadgeVerified: { backgroundColor: '#DCFCE7' },
  trustBadgeError: { backgroundColor: '#FEE2E2' },
  trustBadgeText: { fontWeight: '700', fontSize: 13, color: '#374151' },
  section: { marginTop: 16, borderTopWidth: 1, borderTopColor: '#F3F4F6', paddingTop: 12 },
  sectionTitle: { fontSize: 14, fontWeight: '700', color: '#1B5E20', marginBottom: 8 },
  row: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 4 },
  rowLabel: { color: '#6B7280', fontSize: 13 },
  rowValue: { color: '#111827', fontSize: 13, fontWeight: '600', flexShrink: 1, textAlign: 'right' },
  warning: { color: '#92400E', fontSize: 12, marginTop: 4 },
  errorText: { color: '#B91C1C', fontSize: 12, marginTop: 4 },
});
