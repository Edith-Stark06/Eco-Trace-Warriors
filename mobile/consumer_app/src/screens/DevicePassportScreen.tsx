import React, { useCallback, useEffect, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { deviceAiApi } from '../api/deviceAiApi';
import { submissionsApi } from '../api/submissionsApi';
import { ApiError } from '../api/ApiError';
import { LoadingIndicator } from '../components/LoadingIndicator';
import { ErrorState } from '../components/ErrorState';
import { Card } from '../components/common/Card';
import { theme } from '../theme';
import type {
  DeviceAuditEvent,
  DevicePassportPayload,
  FullTrustComparisonPayload,
  TrustStatusPayload,
} from '../types/device';
import type { PassportVerification } from '../types/verification';
import type { SubmissionLifecycleView } from '../types/submission';

type Props = NativeStackScreenProps<RootStackParamList, 'DevicePassport'>;

// ---------------------------------------------------------------------------
// Presentation-only helpers — no calculation of new values, only formatting
// of numbers/labels the backend already computed and returned.
// ---------------------------------------------------------------------------

type TrustDisplayState =
  | 'VERIFIED'
  | 'PENDING'
  | 'UNANCHORED'
  | 'MISMATCH'
  | 'STALE'
  | 'UNAVAILABLE'
  | 'UNKNOWN';

function mapTrustDisplayState(trust: TrustStatusPayload | null): TrustDisplayState {
  if (!trust) return 'UNAVAILABLE';
  switch (trust.status) {
    case 'VERIFIED':
      return 'VERIFIED';
    case 'ANCHORED':
      return 'PENDING';
    case 'UNANCHORED':
      return 'UNANCHORED';
    case 'MISMATCH':
      return 'MISMATCH';
    case 'STALE':
      return 'STALE';
    default:
      return 'UNKNOWN';
  }
}

const TRUST_COPY: Record<TrustDisplayState, { label: string; tone: 'positive' | 'neutral' | 'negative' }> = {
  VERIFIED: { label: '✓ Blockchain Verified', tone: 'positive' },
  PENDING: { label: 'Verification pending', tone: 'neutral' },
  UNANCHORED: { label: 'Not yet blockchain anchored', tone: 'neutral' },
  MISMATCH: { label: 'Blockchain mismatch detected', tone: 'negative' },
  STALE: { label: 'Blockchain anchor is stale', tone: 'neutral' },
  UNAVAILABLE: { label: 'Blockchain verification unavailable', tone: 'neutral' },
  UNKNOWN: { label: 'Verification status unknown', tone: 'neutral' },
};

const EVENT_LABELS: Record<string, string> = {
  DEVICE_DETECTED: 'Detected',
  DEVICE_CONFIRMED: 'Confirmed',
  DEVICE_REGISTERED: 'Registered',
  DEVICE_ENRICHED: 'AI Classified',
  DEVICE_EXTERNALLY_ANCHORED: 'Blockchain Anchored',
};

function friendlyEventLabel(eventType: string): string {
  return EVENT_LABELS[eventType] ?? eventType;
}

function formatPercent(value: number | null): string {
  if (value === null) return 'Not available';
  return `${Math.round(value * 100)}%`;
}

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return 'Not available';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return 'Not available';
  return date.toLocaleString();
}

function formatKg(grams: number | null | undefined): string {
  if (grams === null || grams === undefined) return 'Not available';
  return `${(grams / 1000).toFixed(2)} kg`;
}

function formatCarbon(kg: number | null | undefined): string {
  if (kg === null || kg === undefined) return 'Not available';
  return `${kg.toFixed(1)} kg CO2e avoided`;
}

function friendlyConditionLabel(condition: string | null, status: string): string {
  if (status === 'UNAVAILABLE' || !condition || condition === 'UNKNOWN') {
    return 'Not yet assessed';
  }
  return condition;
}

function describePassportError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 404) return 'No device was found for this code.';
    if (err.isNetworkError || (err.status !== null && err.status >= 500)) {
      return 'The device intelligence service is unavailable right now. Please try again.';
    }
    return err.message;
  }
  return 'Unable to load this device.';
}

export function DevicePassportScreen({ route }: Props) {
  const { deviceId } = route.params;
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [error, setError] = useState<string | null>(null);
  const [passport, setPassport] = useState<DevicePassportPayload | null>(null);
  const [trust, setTrust] = useState<TrustStatusPayload | null>(null);
  const [trustUnavailable, setTrustUnavailable] = useState(false);
  const [verification, setVerification] = useState<PassportVerification | null>(null);
  const [fullTrust, setFullTrust] = useState<FullTrustComparisonPayload | null>(null);
  const [lifecycle, setLifecycle] = useState<SubmissionLifecycleView | null>(null);

  const load = useCallback(async () => {
    setStatus('loading');
    setError(null);
    try {
      const passportRes = await deviceAiApi.getPassport(deviceId);
      const [trustResult, verifyResult, fullTrustResult, lifecycleResult] = await Promise.allSettled([
        deviceAiApi.getTrustStatus(deviceId),
        deviceAiApi.verifyPassport(deviceId),
        deviceAiApi.getFullTrustStatus(deviceId),
        submissionsApi.getByDevice(deviceId),
      ]);
      setPassport(passportRes.passport);
      setTrust(trustResult.status === 'fulfilled' ? trustResult.value.trust : null);
      setTrustUnavailable(trustResult.status === 'rejected');
      setVerification(verifyResult.status === 'fulfilled' ? verifyResult.value.verification : null);
      setFullTrust(fullTrustResult.status === 'fulfilled' ? fullTrustResult.value.trust : null);
      setLifecycle(lifecycleResult.status === 'fulfilled' ? lifecycleResult.value : null);
      setStatus('ready');
    } catch (err) {
      setError(describePassportError(err));
      setStatus('error');
    }
  }, [deviceId]);

  useEffect(() => {
    let cancelled = false;

    deviceAiApi
      .getPassport(deviceId)
      .then((passportRes) => {
        if (cancelled) return;
        const passportPayload = passportRes.passport;

        return Promise.allSettled([
          deviceAiApi.getTrustStatus(deviceId),
          deviceAiApi.verifyPassport(deviceId),
          deviceAiApi.getFullTrustStatus(deviceId),
          submissionsApi.getByDevice(deviceId),
        ]).then(([trustResult, verifyResult, fullTrustResult, lifecycleResult]) => {
          if (cancelled) return;
          setPassport(passportPayload);
          setTrust(trustResult.status === 'fulfilled' ? trustResult.value.trust : null);
          setTrustUnavailable(trustResult.status === 'rejected');
          setVerification(verifyResult.status === 'fulfilled' ? verifyResult.value.verification : null);
          setFullTrust(fullTrustResult.status === 'fulfilled' ? fullTrustResult.value.trust : null);
          setLifecycle(lifecycleResult.status === 'fulfilled' ? lifecycleResult.value : null);
          setStatus('ready');
        });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(describePassportError(err));
        setStatus('error');
      });

    return () => {
      cancelled = true;
    };
  }, [deviceId]);

  if (status === 'loading') return <LoadingIndicator label="Loading device passport…" />;
  if (status === 'error' || !passport) {
    return <ErrorState message={error ?? 'Device not found.'} onRetry={load} />;
  }

  const trustState = mapTrustDisplayState(trust);
  const trustCopy = TRUST_COPY[trustState];
  const events = passport.audit.events;

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {/* Digital Passport Header Badge */}
      <Card variant="elevated" style={styles.headerCard}>
        <View style={styles.headerTop}>
          <View style={styles.badgePill}>
            <Text style={styles.badgePillText}>DIGITAL PRODUCT PASSPORT</Text>
          </View>
          <Text style={styles.headerIcon}>🛡️</Text>
        </View>

        {passport.eco_id ? (
          <View style={styles.idBlock}>
            <Text style={styles.ecoIdLabel}>EcoID</Text>
            <Text style={styles.ecoId}>{passport.eco_id}</Text>
            <Text style={styles.deviceIdSubtle}>Device ID: {passport.device_id}</Text>
          </View>
        ) : (
          <Text style={styles.deviceIdPrimary}>{passport.device_id}</Text>
        )}

        {(verification?.verification_status === 'VERIFIED' || trust?.status === 'VERIFIED') ? (
          <View style={styles.cardVerifiedRow}>
            <View style={styles.cardVerifiedBadge}>
              <Text style={styles.cardVerifiedText}>✓ Device Verified</Text>
            </View>
          </View>
        ) : null}
      </Card>

      {/* Blockchain Verification Section */}
      <Section title="Blockchain Verification" icon="⛓️">
        <View
          style={[
            styles.trustBadge,
            trustCopy.tone === 'positive' && styles.trustBadgePositive,
            trustCopy.tone === 'negative' && styles.trustBadgeNegative,
          ]}
        >
          <Text
            style={[
              styles.trustBadgeText,
              trustCopy.tone === 'positive' && styles.trustBadgeTextPositive,
              trustCopy.tone === 'negative' && styles.trustBadgeTextNegative,
            ]}
            accessibilityRole="text"
          >
            {trustCopy.label}
          </Text>
        </View>
        {trustUnavailable ? (
          <Text style={styles.unavailableText}>
            Blockchain verification could not be reached. Device information below is still accurate.
          </Text>
        ) : trust ? (
          <View style={styles.table}>
            <Row label="Anchor ID" value={trust.anchor_id ?? 'Not anchored'} isMonospace />
            <Row label="Anchored at" value={formatDateTime(trust.anchored_at)} />
            <Row label="Reason" value={trust.reason} />
            {fullTrust ? (
              <Row
                label="External ledger"
                value={`${fullTrust.provider} / ${fullTrust.external_status}`}
              />
            ) : null}
          </View>
        ) : null}
      </Section>

      {/* AI Intelligence Section */}
      <Section title="AI Intelligence" icon="🤖">
        <View style={styles.table}>
          <Row label="Device type" value={passport.identity.device_type} capitalize />
          <Row label="Classification confidence" value={formatPercent(passport.detection.confidence)} />
          <Row
            label="Condition"
            value={friendlyConditionLabel(passport.condition.condition, passport.condition.status)}
          />
          {passport.brand.brand ? <Row label="Brand" value={passport.brand.brand} /> : null}
        </View>
      </Section>

      {/* Environmental Impact Section */}
      <Section title="Environmental Impact" icon="🌱">
        <View style={styles.table}>
          <Row label="Material weight" value={formatKg(passport.material.total_mass_g)} />
          <Row label="Carbon avoided" value={formatCarbon(passport.carbon.carbon_score)} />
        </View>
        {passport.material.materials.length > 0 ? (
          <View style={styles.materialsList}>
            <Text style={styles.subheading}>Material Composition Breakdown</Text>
            {passport.material.materials.map((item) => (
              <View key={item.material} style={styles.materialRow}>
                <Text style={styles.materialBullet}>•</Text>
                <Text style={styles.materialItem}>
                  {item.material} ({formatKg(item.mass_g)}
                  {item.recoverable ? ', recoverable' : ''}
                  {item.hazardous ? ', hazardous' : ''})
                </Text>
              </View>
            ))}
          </View>
        ) : (
          <Text style={styles.unavailableText}>Material breakdown not yet available.</Text>
        )}
      </Section>

      {/* Device Lifecycle Audit Trail */}
      <Section title="Device Lifecycle" icon="📜">
        {events.length === 0 ? (
          <Text style={styles.unavailableText}>Information unavailable</Text>
        ) : (
          <View style={styles.timelineContainer}>
            {events.map((event, index) => (
              <TimelineEntry key={event.event_id} event={event} isLast={index === events.length - 1} />
            ))}
          </View>
        )}
      </Section>

      {/* Collection & Recycling Lifecycle */}
      <Section title="Collection & Recycling" icon="♻️">
        {lifecycle ? (
          <View style={styles.table}>
            <ChecklistRow label="Collector assigned" done={lifecycle.collectorAssigned} />
            <ChecklistRow label="Pickup accepted" done={lifecycle.pickupAccepted} />
            <ChecklistRow label="Pickup completed" done={lifecycle.collected} />
            <ChecklistRow label="Device received for recycling" done={lifecycle.recyclingStarted} />
            <ChecklistRow label="Recycling completed" done={lifecycle.recycled} />
            {lifecycle.recoveredWeight !== null ? (
              <Row label="Weight recycled" value={`${lifecycle.recoveredWeight} kg`} />
            ) : null}
            {lifecycle.recycledAt ? (
              <Row label="Recycled on" value={formatDateTime(lifecycle.recycledAt)} />
            ) : null}
            {lifecycle.co2Saved !== null ? (
              <Row label="CO2 avoided" value={formatCarbon(lifecycle.co2Saved)} />
            ) : null}
          </View>
        ) : (
          <Text style={styles.unavailableText}>Collection information unavailable</Text>
        )}
      </Section>

      {/* Passport Verification Section */}
      {verification ? (
        <Section title="Passport verification" icon="🔍">
          <View style={styles.table}>
            <Row label="Status" value={verification.verification_status} />
            <Row label="Verified at" value={formatDateTime(verification.verified_at)} />
          </View>
          {verification.warnings.length > 0 ? (
            <View style={styles.warningBox}>
              <Text style={styles.warning}>{verification.warnings.join('; ')}</Text>
            </View>
          ) : null}
          {verification.errors.length > 0 ? (
            <View style={styles.errorBox}>
              <Text style={styles.errorText} accessibilityRole="alert">
                {verification.errors.join('; ')}
              </Text>
            </View>
          ) : null}
        </Section>
      ) : (
        <Section title="Passport verification" icon="🔍">
          <Text style={styles.unavailableText}>Passport verification unavailable.</Text>
        </Section>
      )}
    </ScrollView>
  );
}

function TimelineEntry({ event, isLast }: { event: DeviceAuditEvent; isLast: boolean }) {
  return (
    <View style={styles.timelineRow}>
      <View style={styles.timelineMarkerColumn}>
        <View style={styles.timelineDot} />
        {!isLast ? <View style={styles.timelineLine} /> : null}
      </View>
      <View style={styles.timelineContent}>
        <Text style={styles.timelineLabel}>{friendlyEventLabel(event.event_type)}</Text>
        <Text style={styles.timelineTimestamp}>{formatDateTime(event.timestamp)}</Text>
      </View>
    </View>
  );
}

function Section({ title, icon, children }: { title: string; icon?: string; children: React.ReactNode }) {
  return (
    <Card variant="outlined" style={styles.sectionCard}>
      <View style={styles.sectionHeader}>
        {icon ? <Text style={styles.sectionIcon}>{icon}</Text> : null}
        <Text style={styles.sectionTitle}>{title}</Text>
      </View>
      {children}
    </Card>
  );
}

function Row({ label, value, isMonospace, capitalize }: { label: string; value: string; isMonospace?: boolean; capitalize?: boolean }) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>{label}</Text>
      <Text
        style={[
          styles.rowValue,
          isMonospace && styles.rowValueMono,
          capitalize && styles.rowValueCap,
        ]}
      >
        {value}
      </Text>
    </View>
  );
}

function ChecklistRow({ label, done }: { label: string; done: boolean }) {
  return (
    <View style={styles.checklistRow}>
      <View style={[styles.checklistIconContainer, done && styles.checklistIconContainerDone]}>
        <Text style={[styles.checklistSymbol, done && styles.checklistSymbolDone]}>
          {done ? '✓' : '○'}
        </Text>
      </View>
      <Text style={[styles.checklistLabel, done && styles.checklistDone]}>
        {done ? '✓' : '○'} {label}
      </Text>
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
    gap: theme.spacing.md,
  },
  headerCard: {
    padding: theme.spacing.lg,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.forest[200],
  },
  headerTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: theme.spacing.sm,
  },
  badgePill: {
    backgroundColor: theme.colors.forest[50],
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: 4,
    borderRadius: theme.radius.full,
    borderWidth: 1,
    borderColor: theme.colors.forest[200],
  },
  badgePillText: {
    color: theme.colors.forest[800],
    fontSize: 10,
    fontWeight: theme.typography.weight.bold,
    letterSpacing: 0.8,
  },
  headerIcon: {
    fontSize: 20,
  },
  idBlock: {
    marginTop: theme.spacing.xs,
  },
  ecoIdLabel: {
    fontSize: 11,
    fontWeight: theme.typography.weight.bold,
    color: theme.colors.slate[500],
    letterSpacing: 1.2,
    textTransform: 'uppercase',
  },
  ecoId: {
    fontSize: 24,
    fontWeight: theme.typography.weight.bold,
    color: theme.colors.slate[900],
    fontFamily: 'monospace',
    letterSpacing: 1,
    marginTop: 4,
    marginBottom: 4,
  },
  deviceIdSubtle: {
    fontSize: theme.typography.size.xs,
    color: theme.colors.slate[500],
    marginTop: 2,
    fontFamily: 'monospace',
  },
  deviceIdPrimary: {
    fontSize: 20,
    fontWeight: theme.typography.weight.bold,
    color: theme.colors.slate[900],
    fontFamily: 'monospace',
  },
  cardVerifiedRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: theme.spacing.md,
    paddingTop: theme.spacing.sm,
    borderTopWidth: 1,
    borderTopColor: theme.colors.slate[100],
  },
  cardVerifiedBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: theme.colors.forest[50],
    paddingHorizontal: theme.spacing.sm + 2,
    paddingVertical: 4,
    borderRadius: theme.radius.full,
    borderWidth: 1,
    borderColor: theme.colors.forest[200],
  },
  cardVerifiedText: {
    fontSize: theme.typography.size.xs,
    fontWeight: theme.typography.weight.bold,
    color: theme.colors.forest[800],
  },
  sectionCard: {
    padding: theme.spacing.md,
  },
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: theme.spacing.xs,
    marginBottom: theme.spacing.sm,
    paddingBottom: theme.spacing.xs,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.slate[100],
  },
  sectionIcon: {
    fontSize: 14,
  },
  sectionTitle: {
    fontSize: theme.typography.size.sm,
    fontWeight: theme.typography.weight.bold,
    color: theme.colors.slate[900],
    letterSpacing: 0.3,
  },
  trustBadge: {
    alignSelf: 'flex-start',
    backgroundColor: theme.colors.slate[100],
    borderRadius: theme.radius.sm,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: 6,
    marginBottom: theme.spacing.sm,
    borderWidth: 1,
    borderColor: 'transparent',
  },
  trustBadgePositive: {
    backgroundColor: theme.colors.emerald[50],
    borderColor: theme.colors.emerald[100],
  },
  trustBadgeNegative: {
    backgroundColor: theme.colors.rose[50],
    borderColor: theme.colors.rose[200],
  },
  trustBadgeText: {
    fontWeight: theme.typography.weight.bold,
    fontSize: theme.typography.size.xs,
    color: theme.colors.slate[700],
  },
  trustBadgeTextPositive: {
    color: theme.colors.emerald[800],
  },
  trustBadgeTextNegative: {
    color: theme.colors.rose[800],
  },
  table: {
    gap: 4,
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 5,
    alignItems: 'flex-start',
  },
  rowLabel: {
    color: theme.colors.slate[500],
    fontSize: theme.typography.size.xs,
    flex: 1,
  },
  rowValue: {
    color: theme.colors.slate[900],
    fontSize: theme.typography.size.xs,
    fontWeight: theme.typography.weight.semibold,
    flex: 1.5,
    textAlign: 'right',
  },
  rowValueMono: {
    fontFamily: 'monospace',
    fontSize: 11,
  },
  rowValueCap: {
    textTransform: 'capitalize',
  },
  checklistRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 6,
  },
  checklistIconContainer: {
    display: 'none',
  },
  checklistIconContainerDone: {
    display: 'none',
  },
  checklistSymbol: {
    display: 'none',
  },
  checklistSymbolDone: {
    display: 'none',
  },
  checklistLabel: {
    color: theme.colors.slate[600],
    fontSize: theme.typography.size.xs,
    fontWeight: theme.typography.weight.normal,
  },
  checklistDone: {
    color: theme.colors.forest[700],
    fontWeight: theme.typography.weight.bold,
  },
  subheading: {
    fontSize: theme.typography.size.xs,
    fontWeight: theme.typography.weight.bold,
    color: theme.colors.slate[700],
    marginTop: theme.spacing.sm,
    marginBottom: 4,
  },
  materialsList: {
    marginTop: theme.spacing.xs,
    backgroundColor: theme.colors.slate[50],
    borderRadius: theme.radius.sm,
    padding: theme.spacing.sm,
  },
  materialRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    paddingVertical: 3,
  },
  materialBullet: {
    color: theme.colors.forest[600],
    marginRight: 6,
    fontSize: 12,
  },
  materialItem: {
    color: theme.colors.slate[700],
    fontSize: theme.typography.size.xs,
    flex: 1,
    lineHeight: 16,
  },
  warningBox: {
    backgroundColor: theme.colors.amber[50],
    borderRadius: theme.radius.sm,
    padding: theme.spacing.sm,
    marginTop: theme.spacing.xs,
  },
  warning: {
    color: theme.colors.amber[800],
    fontSize: theme.typography.size.xs,
  },
  errorBox: {
    backgroundColor: theme.colors.rose[50],
    borderRadius: theme.radius.sm,
    padding: theme.spacing.sm,
    marginTop: theme.spacing.xs,
  },
  errorText: {
    color: theme.colors.rose[700],
    fontSize: theme.typography.size.xs,
  },
  unavailableText: {
    color: theme.colors.slate[400],
    fontSize: theme.typography.size.xs,
    fontStyle: 'italic',
    paddingVertical: 4,
  },
  timelineContainer: {
    marginTop: theme.spacing.xs,
    paddingLeft: theme.spacing.xs,
  },
  timelineRow: {
    flexDirection: 'row',
  },
  timelineMarkerColumn: {
    alignItems: 'center',
    width: 20,
  },
  timelineDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: theme.colors.forest[600],
    marginTop: 4,
  },
  timelineLine: {
    width: 2,
    flex: 1,
    backgroundColor: theme.colors.forest[200],
    minHeight: 24,
  },
  timelineContent: {
    flex: 1,
    paddingBottom: theme.spacing.md,
    paddingLeft: theme.spacing.sm,
  },
  timelineLabel: {
    fontSize: theme.typography.size.xs,
    fontWeight: theme.typography.weight.bold,
    color: theme.colors.slate[900],
  },
  timelineTimestamp: {
    fontSize: 11,
    color: theme.colors.slate[500],
    marginTop: 2,
  },
});
