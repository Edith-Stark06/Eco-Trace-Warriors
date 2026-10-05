import React from 'react';
import { FlatList, StyleSheet, Text, View } from 'react-native';
import { useRewards } from '../hooks/useRewards';
import { LoadingIndicator } from '../components/LoadingIndicator';
import { ErrorState } from '../components/ErrorState';
import { EmptyState } from '../components/EmptyState';
import { Card } from '../components/common/Card';
import { StatCard } from '../components/common/StatCard';
import { theme } from '../theme';

/** GreenCoin balance + redemption history — mirrors rewards_screen.dart. */
export function RewardsScreen() {
  const { status, balance, history, error, refresh } = useRewards();

  if (status === 'loading') return <LoadingIndicator label="Loading rewards…" />;
  if (status === 'error') return <ErrorState message={error ?? 'Unable to load rewards.'} onRetry={refresh} />;

  const coins = balance?.greenCoins ?? 0;
  const co2 = (balance?.totalCO2Saved ?? 0).toFixed(1);
  const energy = (balance?.totalEnergySaved ?? 0).toFixed(1);
  const landfill = (balance?.totalLandfillDiverted ?? 0).toFixed(1);

  return (
    <View style={styles.container}>
      {/* Hero GreenCoins Balance Card */}
      <View style={styles.heroWrapper}>
        <View style={styles.heroCard}>
          <View style={styles.badgeRow}>
            <View style={styles.coinBadge}>
              <Text style={styles.coinBadgeIcon}>🪙</Text>
              <Text style={styles.coinBadgeText}>Verified Balance</Text>
            </View>
          </View>
          <Text style={styles.balance} accessibilityLabel={`${coins} GreenCoins`}>
            {coins}
          </Text>
          <Text style={styles.balanceLabel}>GreenCoins</Text>
          <Text style={styles.heroSubtext}>
            Credited automatically when verified recyclers process your e-waste.
          </Text>
        </View>
      </View>

      {/* Environmental Impact Metrics */}
      <View style={styles.statsContainer}>
        <Text style={styles.sectionSubtitle}>VERIFIED ENVIRONMENTAL IMPACT</Text>
        <View style={styles.statsGrid}>
          <StatCard
            label="CO2 saved"
            value={co2}
            unit="kg"
            icon="🌱"
            style={styles.statItem}
          />
          <StatCard
            label="Energy saved"
            value={energy}
            unit="kWh"
            icon="⚡"
            style={styles.statItem}
          />
          <StatCard
            label="Landfill diverted"
            value={landfill}
            unit="kg"
            icon="♻️"
            style={styles.statItem}
          />
        </View>
      </View>

      {/* Reward History */}
      <View style={styles.historyHeader}>
        <Text style={styles.sectionTitle}>History</Text>
        {history.length > 0 && (
          <Text style={styles.historyCount}>{history.length} transactions</Text>
        )}
      </View>

      {history.length === 0 ? (
        <EmptyState message="No rewards earned yet — recycle an item to start earning GreenCoins." />
      ) : (
        <FlatList
          data={history}
          keyExtractor={(item) => item.id}
          contentContainerStyle={styles.listContent}
          renderItem={({ item }) => (
            <Card variant="outlined" style={styles.historyCard}>
              <View style={styles.row}>
                <View style={styles.categoryBadge}>
                  <Text style={styles.categoryIcon}>📦</Text>
                </View>
                <View style={styles.rowDetails}>
                  <Text style={styles.rowTitle}>{item.submission.category}</Text>
                  <Text style={styles.rowDate}>
                    {new Date(item.createdAt).toLocaleDateString(undefined, {
                      year: 'numeric',
                      month: 'short',
                      day: 'numeric',
                    })}
                  </Text>
                </View>
                <View style={styles.pointsBadge}>
                  <Text style={styles.rowPoints}>+{item.points}</Text>
                  <Text style={styles.pointsLabel}>GC</Text>
                </View>
              </View>
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
  heroWrapper: {
    paddingHorizontal: theme.spacing.lg,
    paddingTop: theme.spacing.md,
    paddingBottom: theme.spacing.sm,
  },
  heroCard: {
    backgroundColor: theme.colors.forest[800],
    borderRadius: theme.radius.lg,
    padding: theme.spacing.xl,
    alignItems: 'center',
    ...theme.elevation.md,
  },
  badgeRow: {
    marginBottom: theme.spacing.sm,
  },
  coinBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255, 255, 255, 0.15)',
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: 3,
    borderRadius: theme.radius.full,
    gap: 6,
  },
  coinBadgeIcon: {
    fontSize: 12,
  },
  coinBadgeText: {
    color: theme.colors.forest[100],
    fontSize: theme.typography.size.xs,
    fontWeight: theme.typography.weight.semibold,
    letterSpacing: 0.5,
  },
  balance: {
    fontSize: 44,
    fontWeight: theme.typography.weight.bold,
    color: '#FFFFFF',
    letterSpacing: -1,
  },
  balanceLabel: {
    fontSize: theme.typography.size.sm,
    fontWeight: theme.typography.weight.semibold,
    color: theme.colors.forest[200],
    marginTop: 2,
    letterSpacing: 0.5,
  },
  heroSubtext: {
    fontSize: theme.typography.size.xs,
    color: theme.colors.forest[100],
    textAlign: 'center',
    marginTop: theme.spacing.md,
    lineHeight: 18,
    opacity: 0.9,
  },
  statsContainer: {
    paddingHorizontal: theme.spacing.lg,
    marginTop: theme.spacing.md,
  },
  sectionSubtitle: {
    fontSize: theme.typography.size.xs,
    fontWeight: theme.typography.weight.bold,
    color: theme.colors.slate[500],
    letterSpacing: 0.8,
    marginBottom: theme.spacing.sm,
  },
  statsGrid: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
  },
  statItem: {
    flex: 1,
    paddingVertical: theme.spacing.md,
    paddingHorizontal: theme.spacing.sm,
    alignItems: 'center',
  },
  historyHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: theme.spacing.lg,
    marginTop: theme.spacing.lg,
    marginBottom: theme.spacing.xs,
  },
  sectionTitle: {
    fontSize: theme.typography.size.base,
    fontWeight: theme.typography.weight.bold,
    color: theme.colors.slate[900],
  },
  historyCount: {
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
  row: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  categoryBadge: {
    width: 40,
    height: 40,
    borderRadius: theme.radius.md,
    backgroundColor: theme.colors.forest[50],
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: theme.spacing.md,
  },
  categoryIcon: {
    fontSize: 18,
  },
  rowDetails: {
    flex: 1,
  },
  rowTitle: {
    fontSize: theme.typography.size.sm,
    fontWeight: theme.typography.weight.semibold,
    color: theme.colors.slate[900],
  },
  rowDate: {
    fontSize: theme.typography.size.xs,
    color: theme.colors.slate[500],
    marginTop: 2,
  },
  pointsBadge: {
    flexDirection: 'row',
    alignItems: 'baseline',
    backgroundColor: theme.colors.emerald[50],
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: 4,
    borderRadius: theme.radius.sm,
    gap: 3,
  },
  rowPoints: {
    fontSize: theme.typography.size.sm,
    fontWeight: theme.typography.weight.bold,
    color: theme.colors.emerald[700],
  },
  pointsLabel: {
    fontSize: 10,
    fontWeight: theme.typography.weight.bold,
    color: theme.colors.emerald[600],
  },
});
