import React from 'react';
import { FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { useAuth } from '../auth/AuthContext';
import { useSubmissions } from '../hooks/useSubmissions';
import { useSyncManager } from '../hooks/useSyncManager';
import { LoadingIndicator } from '../components/LoadingIndicator';
import { ErrorState } from '../components/ErrorState';
import { EmptyState } from '../components/EmptyState';
import { NetworkStatusBanner } from '../components/NetworkStatusBanner';
import { Card } from '../components/common/Card';
import { StatusBadge } from '../components/common/StatusBadge';
import { theme } from '../theme';
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
    <Card
      variant="outlined"
      style={styles.submissionCard}
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={`${item.category} pickup, status ${STATUS_LABEL[item.status] ?? item.status}`}
    >
      <View style={styles.cardHeader}>
        <View style={styles.categoryBadge}>
          <Text style={styles.categoryIcon}>📦</Text>
          <Text style={styles.categoryTitle}>{item.category}</Text>
        </View>
        <StatusBadge status={item.status} label={STATUS_LABEL[item.status]} size="sm" />
      </View>

      <View style={styles.cardBody}>
        <View style={styles.infoRow}>
          <Text style={styles.infoIcon}>📍</Text>
          <Text style={styles.addressText} numberOfLines={2}>
            {item.address}
          </Text>
        </View>
        <View style={styles.infoRow}>
          <Text style={styles.infoIcon}>⚖️</Text>
          <Text style={styles.metaText}>
            Est. {item.estimatedWeight} kg • Scheduled {new Date(item.createdAt).toLocaleDateString()}
          </Text>
        </View>
      </View>

      <View style={styles.cardFooter}>
        <Text style={styles.tapPrompt}>Tap to manage pickup →</Text>
        <Text style={styles.rowStatus}>{STATUS_LABEL[item.status] ?? item.status}</Text>
      </View>
    </Card>
  );
}

/** Collector home: assigned/pending tasks + sync status — mirrors home_screen.dart. */
export function DashboardScreen({ navigation }: Props) {
  const insets = useSafeAreaInsets();
  const { user, logout } = useAuth();
  const { status, submissions, error, refresh } = useSubmissions();
  const { isOnline, pendingCount, failedCount } = useSyncManager();

  return (
    <View style={styles.container}>
      {/* Header Operations Bar */}
      <View style={[styles.header, { paddingTop: Math.max(insets.top, theme.spacing.base) + theme.spacing.xs }]}>
        <View style={styles.headerLeft}>
          <View style={styles.opsTag}>
            <View style={styles.opsDot} />
            <Text style={styles.opsTagText}>COLLECTOR OPERATIONS</Text>
          </View>
          <Text style={styles.greeting}>Hi, {user?.fullName ?? 'Collector'}</Text>
          <Text style={styles.headerSubtitle}>{submissions.length} assigned pickup(s)</Text>
        </View>

        <Pressable
          style={styles.logoutBtn}
          onPress={logout}
          accessibilityRole="button"
          accessibilityLabel="Sign out"
        >
          <Text style={styles.logout}>Sign out</Text>
        </Pressable>
      </View>

      <NetworkStatusBanner isOnline={isOnline} pendingCount={pendingCount} failedCount={failedCount} />

      {/* Primary Action Row */}
      <View style={styles.actions}>
        <Pressable
          style={styles.actionButton}
          onPress={() => navigation.navigate('Capture')}
          accessibilityRole="button"
          accessibilityLabel="Capture a new device"
          testID="dashboard-capture-button"
        >
          <Text style={styles.actionButtonIcon}>📸</Text>
          <Text style={styles.actionButtonText}>Capture device</Text>
        </Pressable>

        <Pressable
          style={styles.actionButtonSecondary}
          onPress={() => navigation.navigate('SubmissionHistory')}
          accessibilityRole="button"
          accessibilityLabel="View submission history"
        >
          <Text style={styles.actionButtonSecondaryIcon}>📋</Text>
          <Text style={styles.actionButtonSecondaryText}>History</Text>
        </Pressable>
      </View>

      {/* Assignment Queue Section */}
      <View style={styles.queueHeader}>
        <Text style={styles.sectionTitle}>Pickup Assignment Queue</Text>
        <Text style={styles.queueCount}>{submissions.length} active</Text>
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
          contentContainerStyle={styles.listContent}
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
  container: {
    flex: 1,
    backgroundColor: theme.colors.background.app,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    paddingHorizontal: theme.spacing.lg,
    paddingBottom: theme.spacing.md,
    backgroundColor: theme.colors.surface,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.slate[100],
    marginBottom: theme.spacing.xs,
  },
  headerLeft: {
    flex: 1,
  },
  opsTag: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    marginBottom: 4,
  },
  opsDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: theme.colors.forest[600],
  },
  opsTagText: {
    fontSize: 10,
    fontWeight: theme.typography.weight.bold,
    color: theme.colors.forest[700],
    letterSpacing: 0.8,
  },
  greeting: {
    fontSize: theme.typography.size.xl,
    fontWeight: theme.typography.weight.bold,
    color: theme.colors.slate[900],
  },
  headerSubtitle: {
    fontSize: theme.typography.size.xs,
    color: theme.colors.slate[500],
    marginTop: 2,
  },
  logoutBtn: {
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: theme.radius.sm,
    backgroundColor: theme.colors.rose[50],
  },
  logout: {
    color: theme.colors.rose[700],
    fontSize: theme.typography.size.xs,
    fontWeight: theme.typography.weight.bold,
  },
  actions: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
    paddingHorizontal: theme.spacing.lg,
    marginTop: theme.spacing.sm,
    marginBottom: theme.spacing.md,
  },
  actionButton: {
    flex: 2,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: theme.colors.forest[700],
    borderRadius: theme.radius.md,
    paddingVertical: 14,
    minHeight: 48,
    gap: 8,
    ...theme.elevation.xs,
  },
  actionButtonIcon: {
    fontSize: 16,
  },
  actionButtonText: {
    color: '#FFFFFF',
    fontWeight: theme.typography.weight.bold,
    fontSize: theme.typography.size.sm,
  },
  actionButtonSecondary: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: theme.colors.border.main,
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radius.md,
    paddingVertical: 14,
    minHeight: 48,
    gap: 6,
  },
  actionButtonSecondaryIcon: {
    fontSize: 14,
  },
  actionButtonSecondaryText: {
    color: theme.colors.slate[700],
    fontWeight: theme.typography.weight.semibold,
    fontSize: theme.typography.size.sm,
  },
  queueHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: theme.spacing.lg,
    marginBottom: theme.spacing.xs,
  },
  sectionTitle: {
    fontSize: theme.typography.size.sm,
    fontWeight: theme.typography.weight.bold,
    color: theme.colors.slate[800],
    letterSpacing: 0.3,
  },
  queueCount: {
    fontSize: theme.typography.size.xs,
    color: theme.colors.slate[500],
    fontWeight: theme.typography.weight.medium,
  },
  listContent: {
    paddingHorizontal: theme.spacing.lg,
    paddingTop: theme.spacing.xs,
    paddingBottom: theme.spacing.xxl,
    gap: theme.spacing.sm,
  },
  submissionCard: {
    padding: theme.spacing.md,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: theme.spacing.sm,
  },
  categoryBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  categoryIcon: {
    fontSize: 16,
  },
  categoryTitle: {
    fontSize: theme.typography.size.sm,
    fontWeight: theme.typography.weight.bold,
    color: theme.colors.slate[900],
  },
  cardBody: {
    gap: 6,
    marginBottom: theme.spacing.sm,
  },
  infoRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 6,
  },
  infoIcon: {
    fontSize: 12,
    marginTop: 2,
  },
  addressText: {
    fontSize: theme.typography.size.xs,
    color: theme.colors.slate[700],
    flex: 1,
    lineHeight: 16,
  },
  metaText: {
    fontSize: 11,
    color: theme.colors.slate[500],
  },
  cardFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderTopWidth: 1,
    borderTopColor: theme.colors.slate[100],
    paddingTop: theme.spacing.xs,
    marginTop: 2,
  },
  tapPrompt: {
    fontSize: 11,
    fontWeight: theme.typography.weight.semibold,
    color: theme.colors.forest[700],
  },
  rowStatus: {
    fontSize: 11,
    color: theme.colors.slate[500],
    fontWeight: theme.typography.weight.medium,
  },
});
