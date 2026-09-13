import React, { useCallback, useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { submissionsApi } from '../api/submissionsApi';
import { ApiError } from '../api/ApiError';
import { LoadingIndicator } from '../components/LoadingIndicator';
import { ErrorState } from '../components/ErrorState';
import { Card } from '../components/common/Card';
import { theme } from '../theme';
import type { PublicSubmission, SubmissionStatus } from '../types/submission';

type Props = NativeStackScreenProps<RootStackParamList, 'SubmissionDetail'>;

/** The one action a COLLECTOR can legally take from each status (real backend transitions). */
const NEXT_ACTION: Partial<Record<SubmissionStatus, { label: string; run: (id: string) => Promise<PublicSubmission> }>> = {
  ASSIGNED: { label: 'Accept pickup', run: submissionsApi.accept },
  ACCEPTED: { label: 'Start pickup', run: submissionsApi.start },
  IN_PROGRESS: { label: 'Mark collected', run: submissionsApi.complete },
};

export function SubmissionDetailScreen({ route, navigation }: Props) {
  const { submissionId } = route.params;
  const [submission, setSubmission] = useState<PublicSubmission | null>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [error, setError] = useState<string | null>(null);
  const [actionPending, setActionPending] = useState(false);

  const load = useCallback(async () => {
    setStatus('loading');
    try {
      const result = await submissionsApi.get(submissionId);
      setSubmission(result);
      setStatus('ready');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to load this submission.');
      setStatus('error');
    }
  }, [submissionId]);

  useEffect(() => {
    let cancelled = false;
    submissionsApi
      .get(submissionId)
      .then((result) => {
        if (cancelled) return;
        setSubmission(result);
        setStatus('ready');
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : 'Unable to load this submission.');
        setStatus('error');
      });
    return () => {
      cancelled = true;
    };
  }, [submissionId]);

  const handleAction = async () => {
    if (!submission) return;
    const action = NEXT_ACTION[submission.status];
    if (!action) return;
    setActionPending(true);
    try {
      const updated = await action.run(submission.id);
      setSubmission(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Action failed.');
    } finally {
      setActionPending(false);
    }
  };

  if (status === 'loading') return <LoadingIndicator label="Loading submission…" />;
  if (status === 'error' || !submission) {
    return <ErrorState message={error ?? 'Submission not found.'} onRetry={load} />;
  }

  const action = NEXT_ACTION[submission.status];
  const canRegisterDevice =
    !submission.deviceId && (submission.status === 'ACCEPTED' || submission.status === 'IN_PROGRESS');

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {/* Header Card */}
      <Card variant="elevated" style={styles.heroCard}>
        <View style={styles.heroTop}>
          <Text style={styles.heroEyebrow}>PICKUP DETAILS</Text>
          <View style={styles.statusPill}>
            <Text style={styles.statusPillText}>{submission.status}</Text>
          </View>
        </View>
        <Text style={styles.title}>{submission.category}</Text>
        <Text style={styles.heroMeta}>
          ID: {submission.id}
        </Text>
      </Card>

      {/* Primary Details */}
      <Card variant="outlined" style={styles.detailsCard}>
        <Text style={styles.sectionHeader}>Logistics Information</Text>

        <Field label="Address" value={submission.address} icon="📍" />
        <Field label="Estimated weight" value={`${submission.estimatedWeight} kg`} icon="⚖️" />
        {submission.description ? (
          <Field label="Description" value={submission.description} icon="📝" />
        ) : null}
        <Field
          label="Submitted"
          value={new Date(submission.createdAt).toLocaleString(undefined, {
            dateStyle: 'medium',
            timeStyle: 'short',
          })}
          icon="📅"
        />
        {submission.pickupScheduledAt ? (
          <Field
            label="Pickup scheduled"
            value={new Date(submission.pickupScheduledAt).toLocaleString(undefined, {
              dateStyle: 'medium',
              timeStyle: 'short',
            })}
            icon="⏰"
          />
        ) : null}
        {submission.deviceId ? (
          <Field label="Device" value={submission.deviceId} icon="🛡️" isMono />
        ) : null}
      </Card>

      {error ? (
        <View style={styles.errorBox}>
          <Text style={styles.error} accessibilityRole="alert">
            {error}
          </Text>
        </View>
      ) : null}

      {/* Action Buttons Section */}
      <View style={styles.actionsContainer}>
        {canRegisterDevice ? (
          <Pressable
            style={styles.secondaryButton}
            onPress={() => navigation.navigate('Capture', { submissionId: submission.id })}
            accessibilityRole="button"
            accessibilityLabel="Register device"
            testID="register-device-action"
          >
            <Text style={styles.secondaryButtonIcon}>📷</Text>
            <Text style={styles.secondaryButtonText}>Register device</Text>
          </Pressable>
        ) : null}

        {action ? (
          <Pressable
            style={[styles.button, actionPending && styles.buttonDisabled]}
            onPress={handleAction}
            disabled={actionPending}
            accessibilityRole="button"
            accessibilityLabel={action.label}
            accessibilityState={{ disabled: actionPending, busy: actionPending }}
          >
            <Text style={styles.buttonText}>{actionPending ? 'Working…' : action.label}</Text>
          </Pressable>
        ) : null}
      </View>
    </ScrollView>
  );
}

function Field({ label, value, icon, isMono }: { label: string; value: string; icon?: string; isMono?: boolean }) {
  return (
    <View style={styles.field}>
      <View style={styles.fieldLabelRow}>
        {icon ? <Text style={styles.fieldIcon}>{icon}</Text> : null}
        <Text style={styles.fieldLabel}>{label}</Text>
      </View>
      <Text style={[styles.fieldValue, isMono && styles.fieldValueMono]}>{value}</Text>
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
  heroCard: {
    padding: theme.spacing.lg,
    marginBottom: theme.spacing.md,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.forest[200],
  },
  heroTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: theme.spacing.xs,
  },
  heroEyebrow: {
    fontSize: 11,
    fontWeight: theme.typography.weight.bold,
    color: theme.colors.slate[500],
    letterSpacing: 1,
  },
  statusPill: {
    backgroundColor: theme.colors.forest[50],
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: 3,
    borderRadius: theme.radius.full,
    borderWidth: 1,
    borderColor: theme.colors.forest[200],
  },
  statusPillText: {
    color: theme.colors.forest[800],
    fontSize: 11,
    fontWeight: theme.typography.weight.bold,
  },
  title: {
    fontSize: theme.typography.size.xl,
    fontWeight: theme.typography.weight.bold,
    color: theme.colors.slate[900],
    marginTop: 2,
  },
  heroMeta: {
    fontSize: 11,
    color: theme.colors.slate[500],
    marginTop: 4,
    fontFamily: 'monospace',
  },
  detailsCard: {
    padding: theme.spacing.lg,
  },
  sectionHeader: {
    fontSize: theme.typography.size.xs,
    fontWeight: theme.typography.weight.bold,
    color: theme.colors.slate[500],
    letterSpacing: 0.8,
    textTransform: 'uppercase',
    marginBottom: theme.spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.slate[100],
    paddingBottom: theme.spacing.xs,
  },
  field: {
    marginBottom: theme.spacing.md,
  },
  fieldLabelRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginBottom: 2,
  },
  fieldIcon: {
    fontSize: 12,
  },
  fieldLabel: {
    fontSize: theme.typography.size.xs,
    color: theme.colors.slate[500],
    fontWeight: theme.typography.weight.medium,
  },
  fieldValue: {
    fontSize: theme.typography.size.sm,
    color: theme.colors.slate[900],
    fontWeight: theme.typography.weight.semibold,
    lineHeight: 20,
  },
  fieldValueMono: {
    fontFamily: 'monospace',
    color: theme.colors.forest[800],
    fontSize: theme.typography.size.xs,
  },
  errorBox: {
    backgroundColor: theme.colors.rose[50],
    borderRadius: theme.radius.sm,
    padding: theme.spacing.sm,
  },
  error: {
    color: theme.colors.rose[700],
    fontSize: theme.typography.size.xs,
    fontWeight: theme.typography.weight.medium,
  },
  actionsContainer: {
    gap: theme.spacing.sm,
    marginTop: theme.spacing.xs,
  },
  button: {
    backgroundColor: theme.colors.forest[700],
    borderRadius: theme.radius.md,
    paddingVertical: 14,
    alignItems: 'center',
    minHeight: 48,
    ...theme.elevation.xs,
  },
  buttonDisabled: {
    opacity: 0.6,
  },
  buttonText: {
    color: '#FFFFFF',
    fontWeight: theme.typography.weight.bold,
    fontSize: theme.typography.size.sm,
  },
  secondaryButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: theme.colors.forest[700],
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radius.md,
    paddingVertical: 14,
    minHeight: 48,
    gap: 8,
  },
  secondaryButtonIcon: {
    fontSize: 16,
  },
  secondaryButtonText: {
    color: theme.colors.forest[700],
    fontWeight: theme.typography.weight.bold,
    fontSize: theme.typography.size.sm,
  },
});
