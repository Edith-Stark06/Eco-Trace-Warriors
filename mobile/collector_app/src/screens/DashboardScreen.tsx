import React from 'react';
import { FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { useAuth } from '../auth/AuthContext';
import { useSubmissions } from '../hooks/useSubmissions';
import { useSyncManager } from '../hooks/useSyncManager';
import { LoadingIndicator } from '../components/LoadingIndicator';
import { ErrorState } from '../components/ErrorState';
import { EmptyState } from '../components/EmptyState';
import { NetworkStatusBanner } from '../components/NetworkStatusBanner';
import type { PublicSubmission } from '../types/submission';

type Props = NativeStackScreenProps<RootStackParamList, 'Dashboard'>;

const STATUS_LABEL: Record<string, string> = {
  PENDING: 'Pending',
  ASSIGNED: 'Assigned to you',
  ACCEPTED: 'Accepted',
  IN_PROGRESS: 'In progress',
  COLLECTED: 'Collected',
};

function SubmissionRow({ item, onPress }: { item: PublicSubmission; onPress: () => void }) {
  return (
    <Pressable
      style={styles.row}
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={`${item.category} pickup, status ${STATUS_LABEL[item.status] ?? item.status}`}
    >
      <View style={styles.rowText}>
        <Text style={styles.rowTitle}>{item.category}</Text>
        <Text style={styles.rowSubtitle}>{item.address}</Text>
      </View>
      <Text style={styles.rowStatus}>{STATUS_LABEL[item.status] ?? item.status}</Text>
    </Pressable>
  );
}

/** Collector home: assigned/pending tasks + sync status — mirrors home_screen.dart. */
export function DashboardScreen({ navigation }: Props) {
  const { user, logout } = useAuth();
  const { status, submissions, error, refresh } = useSubmissions();
  const { isOnline, pendingCount, failedCount } = useSyncManager();

  return (
    <View style={styles.container}>
      <NetworkStatusBanner isOnline={isOnline} pendingCount={pendingCount} failedCount={failedCount} />

      <View style={styles.header}>
        <View>
          <Text style={styles.greeting}>Hi, {user?.fullName ?? 'Collector'}</Text>
          <Text style={styles.headerSubtitle}>{submissions.length} assigned pickup(s)</Text>
        </View>
        <Pressable onPress={logout} accessibilityRole="button" accessibilityLabel="Sign out">
          <Text style={styles.logout}>Sign out</Text>
        </Pressable>
      </View>

      <View style={styles.actions}>
        <Pressable
          style={styles.actionButton}
          onPress={() => navigation.navigate('Capture')}
          accessibilityRole="button"
          accessibilityLabel="Capture a new device"
          testID="dashboard-capture-button"
        >
          <Text style={styles.actionButtonText}>Capture device</Text>
        </Pressable>
        <Pressable
          style={styles.actionButtonSecondary}
          onPress={() => navigation.navigate('SubmissionHistory')}
          accessibilityRole="button"
          accessibilityLabel="View submission history"
        >
          <Text style={styles.actionButtonSecondaryText}>History</Text>
        </Pressable>
      </View>

      {status === 'loading' ? (
        <LoadingIndicator label="Loading assigned pickups…" />
      ) : status === 'error' ? (
        <ErrorState message={error ?? 'Something went wrong.'} onRetry={refresh} />
      ) : submissions.length === 0 ? (
        <EmptyState message="No pickups assigned yet." />
      ) : (
        <FlatList
          data={submissions}
          keyExtractor={(item) => item.id}
          renderItem={({ item }) => (
            <SubmissionRow
              item={item}
              onPress={() => navigation.navigate('SubmissionDetail', { submissionId: item.id })}
            />
          )}
          refreshControl={<RefreshControl refreshing={false} onRefresh={refresh} />}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#FFFFFF' },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 16,
  },
  greeting: { fontSize: 20, fontWeight: '700', color: '#1B5E20' },
  headerSubtitle: { fontSize: 13, color: '#6B7280', marginTop: 2 },
  logout: { color: '#B91C1C', fontSize: 14, fontWeight: '600' },
  actions: { flexDirection: 'row', gap: 12, paddingHorizontal: 16, marginBottom: 12 },
  actionButton: {
    flex: 1,
    backgroundColor: '#2E7D32',
    borderRadius: 8,
    paddingVertical: 14,
    alignItems: 'center',
    minHeight: 48,
  },
  actionButtonText: { color: '#FFFFFF', fontWeight: '600' },
  actionButtonSecondary: {
    flex: 1,
    borderWidth: 1,
    borderColor: '#2E7D32',
    borderRadius: 8,
    paddingVertical: 14,
    alignItems: 'center',
    minHeight: 48,
  },
  actionButtonSecondaryText: { color: '#2E7D32', fontWeight: '600' },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 14,
    paddingHorizontal: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#F3F4F6',
    minHeight: 44,
  },
  rowText: { flex: 1 },
  rowTitle: { fontSize: 15, fontWeight: '600', color: '#111827' },
  rowSubtitle: { fontSize: 13, color: '#6B7280', marginTop: 2 },
  rowStatus: { fontSize: 13, color: '#2E7D32', fontWeight: '600' },
});
