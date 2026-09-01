import React, { useCallback, useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { submissionsApi } from '../api/submissionsApi';
import { ApiError } from '../api/ApiError';
import { LoadingIndicator } from '../components/LoadingIndicator';
import { ErrorState } from '../components/ErrorState';
import type { PublicSubmission, SubmissionStatus } from '../types/submission';

type Props = NativeStackScreenProps<RootStackParamList, 'SubmissionDetail'>;

/** The one action a COLLECTOR can legally take from each status (real backend transitions). */
const NEXT_ACTION: Partial<Record<SubmissionStatus, { label: string; run: (id: string) => Promise<PublicSubmission> }>> = {
  ASSIGNED: { label: 'Accept pickup', run: submissionsApi.accept },
  ACCEPTED: { label: 'Start pickup', run: submissionsApi.start },
  IN_PROGRESS: { label: 'Mark collected', run: submissionsApi.complete },
};

/**
 * Real Submission record detail + status transition actions.
 *
 * Note: the backend's Submission model (this screen) and device_ai's
 * Device/passport/trust model are two independent systems with no
 * `deviceId` foreign key between them today (see
 * docs/engineering/03_ARCHITECTURE.md — "two-system split"). Showing a
 * blockchain-anchor/passport/trust status here would require either a
 * schema change or guessing a link that does not exist, so this screen
 * intentionally shows only the real, correctly-linked Submission
 * lifecycle rather than fabricating a passport/trust section.
 */
export function SubmissionDetailScreen({ route }: Props) {
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

  return (
    <ScrollView style={styles.container}>
      <Text style={styles.title}>{submission.category}</Text>
      <View style={styles.badge}>
        <Text style={styles.badgeText}>{submission.status}</Text>
      </View>

      <Field label="Address" value={submission.address} />
      <Field label="Estimated weight" value={`${submission.estimatedWeight} kg`} />
      {submission.description ? <Field label="Description" value={submission.description} /> : null}
      <Field label="Submitted" value={new Date(submission.createdAt).toLocaleString()} />
      {submission.pickupScheduledAt ? (
        <Field label="Pickup scheduled" value={new Date(submission.pickupScheduledAt).toLocaleString()} />
      ) : null}

      {error ? (
        <Text style={styles.error} accessibilityRole="alert">
          {error}
        </Text>
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
    </ScrollView>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.field}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <Text style={styles.fieldValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#FFFFFF', padding: 16 },
  title: { fontSize: 20, fontWeight: '700', color: '#1B5E20' },
  badge: {
    alignSelf: 'flex-start',
    backgroundColor: '#DCFCE7',
    borderRadius: 6,
    paddingHorizontal: 10,
    paddingVertical: 4,
    marginTop: 8,
    marginBottom: 16,
  },
  badgeText: { color: '#166534', fontWeight: '700', fontSize: 12 },
  field: { marginBottom: 12 },
  fieldLabel: { fontSize: 12, color: '#6B7280' },
  fieldValue: { fontSize: 15, color: '#111827', marginTop: 2 },
  error: { color: '#B91C1C', marginTop: 8, marginBottom: 8, fontSize: 13 },
  button: { backgroundColor: '#2E7D32', borderRadius: 8, paddingVertical: 14, alignItems: 'center', marginTop: 16, minHeight: 48 },
  buttonDisabled: { opacity: 0.6 },
  buttonText: { color: '#FFFFFF', fontWeight: '600' },
});
