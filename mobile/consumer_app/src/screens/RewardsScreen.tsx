import React from 'react';
import { FlatList, StyleSheet, Text, View } from 'react-native';
import { useRewards } from '../hooks/useRewards';
import { LoadingIndicator } from '../components/LoadingIndicator';
import { ErrorState } from '../components/ErrorState';
import { EmptyState } from '../components/EmptyState';

/** GreenCoin balance + redemption history — mirrors rewards_screen.dart. */
export function RewardsScreen() {
  const { status, balance, history, error, refresh } = useRewards();

  if (status === 'loading') return <LoadingIndicator label="Loading rewards…" />;
  if (status === 'error') return <ErrorState message={error ?? 'Unable to load rewards.'} onRetry={refresh} />;

  return (
    <View style={styles.container}>
      <View style={styles.summary}>
        <Text style={styles.balance} accessibilityLabel={`${balance?.greenCoins ?? 0} GreenCoins`}>
          {balance?.greenCoins ?? 0}
        </Text>
        <Text style={styles.balanceLabel}>GreenCoins</Text>
        <View style={styles.statsRow}>
          <Stat label="CO2 saved" value={`${(balance?.totalCO2Saved ?? 0).toFixed(1)} kg`} />
          <Stat label="Energy saved" value={`${(balance?.totalEnergySaved ?? 0).toFixed(1)} kWh`} />
          <Stat label="Landfill diverted" value={`${(balance?.totalLandfillDiverted ?? 0).toFixed(1)} kg`} />
        </View>
      </View>

      <Text style={styles.sectionTitle}>History</Text>
      {history.length === 0 ? (
        <EmptyState message="No rewards earned yet — recycle an item to start earning GreenCoins." />
      ) : (
        <FlatList
          data={history}
          keyExtractor={(item) => item.id}
          renderItem={({ item }) => (
            <View style={styles.row}>
              <View>
                <Text style={styles.rowTitle}>{item.submission.category}</Text>
                <Text style={styles.rowDate}>{new Date(item.createdAt).toLocaleDateString()}</Text>
              </View>
              <Text style={styles.rowPoints}>+{item.points}</Text>
            </View>
          )}
        />
      )}
    </View>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.stat}>
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#FFFFFF' },
  summary: { backgroundColor: '#F0FDF4', padding: 20, alignItems: 'center' },
  balance: { fontSize: 40, fontWeight: '800', color: '#166534' },
  balanceLabel: { fontSize: 13, color: '#166534', marginTop: 2 },
  statsRow: { flexDirection: 'row', justifyContent: 'space-between', width: '100%', marginTop: 16 },
  stat: { alignItems: 'center', flex: 1 },
  statValue: { fontSize: 14, fontWeight: '700', color: '#111827' },
  statLabel: { fontSize: 11, color: '#6B7280', marginTop: 2, textAlign: 'center' },
  sectionTitle: { fontSize: 14, fontWeight: '700', color: '#1B5E20', margin: 16, marginBottom: 4 },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 12, paddingHorizontal: 16, borderBottomWidth: 1, borderBottomColor: '#F3F4F6', minHeight: 44 },
  rowTitle: { fontSize: 14, fontWeight: '600', color: '#111827' },
  rowDate: { fontSize: 12, color: '#6B7280', marginTop: 2 },
  rowPoints: { fontSize: 15, fontWeight: '700', color: '#059669' },
});
