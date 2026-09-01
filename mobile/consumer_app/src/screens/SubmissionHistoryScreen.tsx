import React from 'react';
import { FlatList, StyleSheet, Text, View } from 'react-native';
import { useSubmissions } from '../hooks/useSubmissions';
import { useSyncManager } from '../hooks/useSyncManager';
import { LoadingIndicator } from '../components/LoadingIndicator';
import { ErrorState } from '../components/ErrorState';
import { EmptyState } from '../components/EmptyState';

/** The consumer's own reported submissions, plus any offline-queued reports. */
export function SubmissionHistoryScreen() {
  const { status, submissions, error, refresh } = useSubmissions();
  const { queue, isSyncing, syncNow } = useSyncManager();

  if (status === 'loading') return <LoadingIndicator label="Loading your submissions…" />;
  if (status === 'error') return <ErrorState message={error ?? 'Unable to load your submissions.'} onRetry={refresh} />;

  const failed = queue.filter((i) => i.status === 'failed');
  const pending = queue.filter((i) => i.status !== 'failed');

  return (
    <View style={styles.container}>
      {failed.length > 0 && (
        <View style={styles.failedBanner}>
          <Text style={styles.failedText}>{failed.length} report(s) failed to submit</Text>
          <Text onPress={syncNow} accessibilityRole="button" accessibilityLabel="Retry" style={styles.retryLink}>
            {isSyncing ? 'Retrying…' : 'Retry'}
          </Text>
        </View>
      )}
      {pending.length > 0 && <Text style={styles.pendingNote}>{pending.length} report(s) queued</Text>}

      {submissions.length === 0 ? (
        <EmptyState message="No reports submitted yet." />
      ) : (
        <FlatList
          data={submissions}
          keyExtractor={(item) => item.id}
          renderItem={({ item }) => (
            <View style={styles.row} accessibilityLabel={`${item.category}, status ${item.status}`}>
              <Text style={styles.rowTitle}>{item.category}</Text>
              <Text style={styles.rowStatus}>{item.status}</Text>
            </View>
          )}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#FFFFFF' },
  failedBanner: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', backgroundColor: '#FEE2E2', padding: 12 },
  failedText: { color: '#991B1B', fontSize: 13 },
  retryLink: { color: '#B91C1C', fontWeight: '700', fontSize: 13 },
  pendingNote: { fontSize: 13, color: '#92400E', backgroundColor: '#FEF3C7', padding: 12 },
  row: { paddingVertical: 14, paddingHorizontal: 16, borderBottomWidth: 1, borderBottomColor: '#F3F4F6', minHeight: 44 },
  rowTitle: { fontSize: 15, fontWeight: '600', color: '#111827' },
  rowStatus: { fontSize: 13, color: '#2E7D32', marginTop: 2 },
});
