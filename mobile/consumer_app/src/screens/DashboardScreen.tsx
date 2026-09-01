import React from 'react';
import { ScrollView, Pressable, StyleSheet, Text, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { useAuth } from '../auth/AuthContext';
import { useRewards } from '../hooks/useRewards';
import { useSyncManager } from '../hooks/useSyncManager';
import { NetworkStatusBanner } from '../components/NetworkStatusBanner';
import { LoadingIndicator } from '../components/LoadingIndicator';

type Props = NativeStackScreenProps<RootStackParamList, 'Dashboard'>;

const ACTIONS: { key: keyof RootStackParamList; label: string; testID: string }[] = [
  { key: 'ReportWaste', label: 'Report e-waste', testID: 'dashboard-report-button' },
  { key: 'Scan', label: 'Verify a device', testID: 'dashboard-scan-button' },
  { key: 'Rewards', label: 'GreenCoins & rewards', testID: 'dashboard-rewards-button' },
  { key: 'SubmissionHistory', label: 'My submissions', testID: 'dashboard-history-button' },
  { key: 'Education', label: 'Learn about e-waste', testID: 'dashboard-education-button' },
];

/** Consumer home — mirrors home_screen.dart: quick actions + GreenCoin balance. */
export function DashboardScreen({ navigation }: Props) {
  const { user } = useAuth();
  const { status, balance } = useRewards();
  const { isOnline, pendingCount, failedCount } = useSyncManager();

  return (
    <ScrollView style={styles.container}>
      <NetworkStatusBanner isOnline={isOnline} pendingCount={pendingCount} failedCount={failedCount} />

      <View style={styles.header}>
        <Text style={styles.greeting}>Hi, {user?.fullName ?? 'there'}</Text>
        {status === 'loading' ? (
          <LoadingIndicator />
        ) : (
          <Text style={styles.balance} accessibilityLabel={`${balance?.greenCoins ?? 0} GreenCoins`}>
            {balance?.greenCoins ?? 0} GreenCoins
          </Text>
        )}
      </View>

      <View style={styles.grid}>
        {ACTIONS.map((action) => (
          <Pressable
            key={action.key}
            style={styles.card}
            onPress={() => navigation.navigate(action.key as never)}
            accessibilityRole="button"
            accessibilityLabel={action.label}
            testID={action.testID}
          >
            <Text style={styles.cardText}>{action.label}</Text>
          </Pressable>
        ))}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#FFFFFF' },
  header: { padding: 20 },
  greeting: { fontSize: 22, fontWeight: '700', color: '#1B5E20' },
  balance: { fontSize: 16, color: '#059669', fontWeight: '600', marginTop: 8 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', paddingHorizontal: 12, gap: 12 },
  card: {
    width: '46%',
    backgroundColor: '#F0FDF4',
    borderRadius: 12,
    padding: 16,
    minHeight: 88,
    justifyContent: 'center',
    marginBottom: 4,
  },
  cardText: { fontSize: 15, fontWeight: '600', color: '#166534' },
});
