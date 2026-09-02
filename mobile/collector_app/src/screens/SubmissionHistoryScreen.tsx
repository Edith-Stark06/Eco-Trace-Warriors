import React from 'react';
import { FlatList, Pressable, StyleSheet, Text, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { useSubmissions } from '../hooks/useSubmissions';
import { useSyncManager } from '../hooks/useSyncManager';
import { LoadingIndicator } from '../components/LoadingIndicator';
import { ErrorState } from '../components/ErrorState';
import { EmptyState } from '../components/EmptyState';

type Props = NativeStackScreenProps<RootStackParamList, 'SubmissionHistory'>;

/**
 * Assigned-pickup submission history, plus offline device-confirmation
 * queue status with retry — mirrors submission_history_screen.dart.
 */
export function SubmissionHistoryScreen({ navigation }: Props) {
  const { status, submissions, error, refresh } = useSubmissions();
  const { queue, syncNow, isSyncing } = useSyncManager();

  if (status === 'loading') return <LoadingIndicator label="Loading history…" />;
  if (status === 'error') return <ErrorState message={error ?? 'Unable to load history.'} onRetry={refresh} />;

  const failedQueueItems = queue.filter((item) => item.status === 'failed');
  const conflictQueueItems = queue.filter((item) => item.status === 'conflict');
  const pendingQueueItems = queue.filter((item) => item.status === 'pending' || item.status === 'syncing');

  return (
    <View style={styles.container}>
      {failedQueueItems.length > 0 && (
        <View style={styles.failedSection}>
          <Text style={styles.sectionTitle}>Failed to sync ({failedQueueItems.length})</Text>
          {failedQueueItems.map((item) => (
            <View key={item.id} style={styles.failedRow}>
              <Text style={styles.failedText}>{item.deviceType} — {item.lastError}</Text>
            </View>
          ))}
          <Pressable
            style={styles.retryButton}
            onPress={syncNow}
            disabled={isSyncing}
            accessibilityRole="button"
            accessibilityLabel="Retry failed device confirmations"
          >
            <Text style={styles.retryButtonText}>{isSyncing ? 'Retrying…' : 'Retry all'}</Text>
          </Pressable>
        </View>
      )}

      {conflictQueueItems.length > 0 && (
        <View style={styles.conflictSection}>
          <Text style={styles.conflictSectionTitle}>Needs your attention ({conflictQueueItems.length})</Text>
          {conflictQueueItems.map((item) => (
            <View key={item.id} style={styles.conflictRow}>
              <Text style={styles.conflictText} accessibilityRole="alert">
                {item.deviceType} was already finalized elsewhere — check its current status; retrying will not help.
              </Text>
            </View>
          ))}
        </View>
      )}

      {pendingQueueItems.length > 0 && (
        <Text style={styles.pendingNote}>{pendingQueueItems.length} device confirmation(s) queued, pending sync</Text>
      )}

      {submissions.length === 0 ? (
        <EmptyState message="No submitted pickups yet." />
      ) : (
        <FlatList
          data={submissions}
          keyExtractor={(item) => item.id}
          renderItem={({ item }) => (
            <Pressable
              style={styles.row}
              onPress={() => navigation.navigate('SubmissionDetail', { submissionId: item.id })}
              accessibilityRole="button"
              accessibilityLabel={`${item.category}, status ${item.status}`}
            >
              <Text style={styles.rowTitle}>{item.category}</Text>
              <Text style={styles.rowStatus}>{item.status}</Text>
            </Pressable>
          )}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#FFFFFF' },
  sectionTitle: { fontSize: 14, fontWeight: '700', color: '#991B1B', margin: 16, marginBottom: 4 },
  failedSection: { backgroundColor: '#FEF2F2', paddingBottom: 8 },
  failedRow: { paddingHorizontal: 16, paddingVertical: 4 },
  failedText: { fontSize: 13, color: '#991B1B' },
  retryButton: { marginHorizontal: 16, marginTop: 8, backgroundColor: '#B91C1C', borderRadius: 6, paddingVertical: 8, alignItems: 'center', minHeight: 40 },
  retryButtonText: { color: '#FFFFFF', fontWeight: '600', fontSize: 13 },
  conflictSection: { backgroundColor: '#FEF3C7', paddingBottom: 8 },
  conflictSectionTitle: { fontSize: 14, fontWeight: '700', color: '#92400E', margin: 16, marginBottom: 4 },
  conflictRow: { paddingHorizontal: 16, paddingVertical: 4 },
  conflictText: { fontSize: 13, color: '#92400E' },
  pendingNote: { fontSize: 13, color: '#92400E', backgroundColor: '#FEF3C7', padding: 12 },
  row: { paddingVertical: 14, paddingHorizontal: 16, borderBottomWidth: 1, borderBottomColor: '#F3F4F6', minHeight: 44 },
  rowTitle: { fontSize: 15, fontWeight: '600', color: '#111827' },
  rowStatus: { fontSize: 13, color: '#2E7D32', marginTop: 2 },
});
