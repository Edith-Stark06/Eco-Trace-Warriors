import React from 'react';
import { FlatList, Pressable, StyleSheet, Text, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { useSubmissions } from '../hooks/useSubmissions';
import { useSyncManager } from '../hooks/useSyncManager';
import { LoadingIndicator } from '../components/LoadingIndicator';
import { ErrorState } from '../components/ErrorState';
import { EmptyState } from '../components/EmptyState';
import { Card } from '../components/common/Card';
import { StatusBadge } from '../components/common/StatusBadge';
import { theme } from '../theme';

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
      {/* Offline Sync Queue Banners */}
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
        <View style={styles.pendingBanner}>
          <Text style={styles.pendingNote}>
            ⏳ {pendingQueueItems.length} device confirmation(s) queued, pending sync
          </Text>
        </View>
      )}

      <View style={styles.listHeader}>
        <Text style={styles.listTitle}>All Assigned Pickups</Text>
        <Text style={styles.listCount}>{submissions.length} total</Text>
      </View>

      {submissions.length === 0 ? (
        <EmptyState message="No submitted pickups yet." />
      ) : (
        <FlatList
          data={submissions}
          keyExtractor={(item) => item.id}
          contentContainerStyle={styles.listContent}
          renderItem={({ item }) => (
            <Card
              variant="outlined"
              style={styles.historyCard}
              onPress={() => navigation.navigate('SubmissionDetail', { submissionId: item.id })}
              accessibilityRole="button"
              accessibilityLabel={`${item.category}, status ${item.status}`}
            >
              <View style={styles.cardTop}>
                <View style={styles.categoryBadge}>
                  <Text style={styles.categoryIcon}>📦</Text>
                  <Text style={styles.rowTitle}>{item.category}</Text>
                </View>
                <StatusBadge status={item.status} size="sm" />
              </View>

              <View style={styles.cardMeta}>
                <Text style={styles.metaAddress} numberOfLines={1}>
                  📍 {item.address}
                </Text>
                <Text style={styles.metaDate}>
                  📅 {new Date(item.createdAt).toLocaleDateString()}
                </Text>
              </View>

              <Text style={styles.rowStatus}>{item.status}</Text>
            </Card>
          )}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.colors.background.app,
  },
  sectionTitle: {
    fontSize: theme.typography.size.xs,
    fontWeight: theme.typography.weight.bold,
    color: theme.colors.rose[700],
    marginHorizontal: theme.spacing.lg,
    marginTop: theme.spacing.md,
    marginBottom: 4,
  },
  failedSection: {
    backgroundColor: theme.colors.rose[50],
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.rose[200],
    paddingBottom: theme.spacing.md,
  },
  failedRow: {
    paddingHorizontal: theme.spacing.lg,
    paddingVertical: 3,
  },
  failedText: {
    fontSize: theme.typography.size.xs,
    color: theme.colors.rose[700],
  },
  retryButton: {
    marginHorizontal: theme.spacing.lg,
    marginTop: theme.spacing.sm,
    backgroundColor: theme.colors.rose[700],
    borderRadius: theme.radius.sm,
    paddingVertical: 8,
    alignItems: 'center',
    minHeight: 40,
    justifyContent: 'center',
  },
  retryButtonText: {
    color: '#FFFFFF',
    fontWeight: theme.typography.weight.bold,
    fontSize: theme.typography.size.xs,
  },
  conflictSection: {
    backgroundColor: theme.colors.amber[50],
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.amber[100],
    paddingBottom: theme.spacing.md,
  },
  conflictSectionTitle: {
    fontSize: theme.typography.size.xs,
    fontWeight: theme.typography.weight.bold,
    color: theme.colors.amber[800],
    marginHorizontal: theme.spacing.lg,
    marginTop: theme.spacing.md,
    marginBottom: 4,
  },
  conflictRow: {
    paddingHorizontal: theme.spacing.lg,
    paddingVertical: 3,
  },
  conflictText: {
    fontSize: theme.typography.size.xs,
    color: theme.colors.amber[800],
    lineHeight: 16,
  },
  pendingBanner: {
    backgroundColor: theme.colors.amber[50],
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.amber[100],
  },
  pendingNote: {
    fontSize: theme.typography.size.xs,
    color: theme.colors.amber[800],
    padding: theme.spacing.md,
    fontWeight: theme.typography.weight.medium,
  },
  listHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: theme.spacing.lg,
    paddingTop: theme.spacing.md,
    paddingBottom: theme.spacing.xs,
  },
  listTitle: {
    fontSize: theme.typography.size.sm,
    fontWeight: theme.typography.weight.bold,
    color: theme.colors.slate[800],
  },
  listCount: {
    fontSize: theme.typography.size.xs,
    color: theme.colors.slate[500],
  },
  listContent: {
    paddingHorizontal: theme.spacing.lg,
    paddingTop: theme.spacing.xs,
    paddingBottom: theme.spacing.xxl,
    gap: theme.spacing.sm,
  },
  historyCard: {
    padding: theme.spacing.md,
  },
  cardTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: theme.spacing.xs,
  },
  categoryBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  categoryIcon: {
    fontSize: 16,
  },
  rowTitle: {
    fontSize: theme.typography.size.sm,
    fontWeight: theme.typography.weight.bold,
    color: theme.colors.slate[900],
  },
  cardMeta: {
    gap: 2,
    marginBottom: 4,
  },
  metaAddress: {
    fontSize: theme.typography.size.xs,
    color: theme.colors.slate[600],
  },
  metaDate: {
    fontSize: 11,
    color: theme.colors.slate[400],
  },
  rowStatus: {
    display: 'none',
  },
});
