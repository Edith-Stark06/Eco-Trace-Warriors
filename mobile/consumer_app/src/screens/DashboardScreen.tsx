import React from 'react';
import { ScrollView, Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { useAuth } from '../auth/AuthContext';
import { useRewards } from '../hooks/useRewards';
import { useSyncManager } from '../hooks/useSyncManager';
import { NetworkStatusBanner } from '../components/NetworkStatusBanner';
import { LoadingIndicator } from '../components/LoadingIndicator';
import { Card } from '../components/common/Card';
import { colors, radius, shadows, spacing, typography } from '../theme';

type Props = NativeStackScreenProps<RootStackParamList, 'Dashboard'>;

/**
 * Consumer home — modern sustainability companion dashboard.
 * Clear visual hierarchy: Greeting -> GreenCoins & Impact -> Primary "Report" CTA -> Secondary actions grid.
 */
export function DashboardScreen({ navigation }: Props) {
  const insets = useSafeAreaInsets();
  const { user } = useAuth();
  const { status, balance } = useRewards();
  const { isOnline, pendingCount, failedCount } = useSyncManager();

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {/* Top Header */}
      <View style={[styles.header, { paddingTop: Math.max(insets.top, spacing.base) + spacing.xs }]}>
        <View style={styles.headerTextContainer}>
          <Text style={styles.brandTag}>ECOTRACE INDIA</Text>
          <Text style={styles.greeting}>Hi, {user?.fullName ?? 'there'}</Text>
        </View>
        <Pressable
          style={styles.profileAvatar}
          onPress={() => navigation.navigate('Profile')}
          accessibilityRole="button"
          accessibilityLabel="View profile"
        >
          <Text style={styles.profileAvatarText}>
            {(user?.fullName?.[0] ?? 'U').toUpperCase()}
          </Text>
        </Pressable>
      </View>

      <NetworkStatusBanner isOnline={isOnline} pendingCount={pendingCount} failedCount={failedCount} />

      {/* Hero GreenCoins & Environmental Impact Card */}
      <Card style={styles.heroCard}>
        <View style={styles.balanceHeader}>
          <View>
            <Text style={styles.balanceSubtext}>REWARDS BALANCE</Text>
            {status === 'loading' ? (
              <View style={styles.balanceLoading}>
                <LoadingIndicator />
              </View>
            ) : (
              <View style={styles.balanceRow}>
                <Text
                  style={styles.balanceNumber}
                  accessibilityLabel={`${balance?.greenCoins ?? 0} GreenCoins`}
                >
                  {balance?.greenCoins ?? 0}
                </Text>
                <Text style={styles.balanceCurrency}>GreenCoins</Text>
              </View>
            )}
          </View>
          <View style={styles.coinBadge}>
            <Text style={styles.coinBadgeIcon}>🪙</Text>
          </View>
        </View>

        {/* 3-Part Micro Environmental Impact Summary */}
        <View style={styles.impactDivider} />
        <View style={styles.impactRow}>
          <View style={styles.impactItem}>
            <Text style={styles.impactValue}>{(balance?.totalCO2Saved ?? 0).toFixed(1)}</Text>
            <Text style={styles.impactLabel}>kg CO2e avoided</Text>
          </View>
          <View style={styles.impactSeparator} />
          <View style={styles.impactItem}>
            <Text style={styles.impactValue}>{(balance?.totalEnergySaved ?? 0).toFixed(1)}</Text>
            <Text style={styles.impactLabel}>kWh conserved</Text>
          </View>
          <View style={styles.impactSeparator} />
          <View style={styles.impactItem}>
            <Text style={styles.impactValue}>{(balance?.totalLandfillDiverted ?? 0).toFixed(1)}</Text>
            <Text style={styles.impactLabel}>kg landfill avoided</Text>
          </View>
        </View>
      </Card>

      {/* Primary Hero Action: Report Waste */}
      <Pressable
        style={({ pressed }) => [styles.primaryActionCard, pressed && styles.pressed]}
        onPress={() => navigation.navigate('ReportWaste')}
        accessibilityRole="button"
        accessibilityLabel="Report e-waste"
        testID="dashboard-report-button"
      >
        <View style={styles.primaryActionLeft}>
          <View style={styles.primaryActionIconContainer}>
            <Text style={styles.primaryActionIcon}>♻</Text>
          </View>
          <View style={styles.primaryActionTextCol}>
            <Text style={styles.primaryActionTitle}>Report E-Waste</Text>
            <Text style={styles.primaryActionDesc}>
              Request doorstep collection & earn GreenCoins
            </Text>
          </View>
        </View>
        <View style={styles.primaryActionArrow}>
          <Text style={styles.primaryActionArrowText}>→</Text>
        </View>
      </Pressable>

      {/* Section Title */}
      <Text style={styles.sectionHeader}>Services & Discovery</Text>

      {/* Secondary Actions 2x2 Grid */}
      <View style={styles.grid}>
        {/* Verify Device / Scan */}
        <Pressable
          style={({ pressed }) => [styles.gridCard, pressed && styles.pressed]}
          onPress={() => navigation.navigate('Scan')}
          accessibilityRole="button"
          accessibilityLabel="Verify a device"
          testID="dashboard-scan-button"
        >
          <View style={[styles.gridIconContainer, { backgroundColor: colors.tech.surface }]}>
            <Text style={styles.gridIcon}>🔍</Text>
          </View>
          <Text style={styles.gridCardTitle}>Verify a device</Text>
          <Text style={styles.gridCardSubtitle}>Scan QR to view digital passport & trust state</Text>
        </Pressable>

        {/* My Submissions */}
        <Pressable
          style={({ pressed }) => [styles.gridCard, pressed && styles.pressed]}
          onPress={() => navigation.navigate('SubmissionHistory')}
          accessibilityRole="button"
          accessibilityLabel="My submissions"
          testID="dashboard-history-button"
        >
          <View style={[styles.gridIconContainer, { backgroundColor: '#F3E8FF' }]}>
            <Text style={styles.gridIcon}>📋</Text>
          </View>
          <Text style={styles.gridCardTitle}>My submissions</Text>
          <Text style={styles.gridCardSubtitle}>Track real-time pickup & recycling lifecycle</Text>
        </Pressable>

        {/* GreenCoins & Rewards */}
        <Pressable
          style={({ pressed }) => [styles.gridCard, pressed && styles.pressed]}
          onPress={() => navigation.navigate('Rewards')}
          accessibilityRole="button"
          accessibilityLabel="GreenCoins & rewards"
          testID="dashboard-rewards-button"
        >
          <View style={[styles.gridIconContainer, { backgroundColor: '#FEF3C7' }]}>
            <Text style={styles.gridIcon}>🏆</Text>
          </View>
          <Text style={styles.gridCardTitle}>GreenCoins & rewards</Text>
          <Text style={styles.gridCardSubtitle}>Review balance, impact ledger & reward points</Text>
        </Pressable>

        {/* Learn about E-waste */}
        <Pressable
          style={({ pressed }) => [styles.gridCard, pressed && styles.pressed]}
          onPress={() => navigation.navigate('Education')}
          accessibilityRole="button"
          accessibilityLabel="Learn about e-waste"
          testID="dashboard-education-button"
        >
          <View style={[styles.gridIconContainer, { backgroundColor: colors.primary.surface }]}>
            <Text style={styles.gridIcon}>🌱</Text>
          </View>
          <Text style={styles.gridCardTitle}>Learn about e-waste</Text>
          <Text style={styles.gridCardSubtitle}>Circular materials, toxic prevention & safety</Text>
        </Pressable>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background.app,
  },
  content: {
    paddingBottom: spacing.xxl,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.base,
    backgroundColor: colors.surface,
    borderBottomWidth: 1,
    borderBottomColor: colors.border.light,
    marginBottom: spacing.base,
  },
  headerTextContainer: {
    flex: 1,
  },
  brandTag: {
    fontSize: typography.sizes.micro + 1,
    fontWeight: typography.weights.bold,
    color: colors.primary.main,
    letterSpacing: 1.5,
    marginBottom: spacing.xxs,
  },
  greeting: {
    fontSize: typography.sizes.title,
    fontWeight: typography.weights.heavy,
    color: colors.text.primary,
    letterSpacing: -0.5,
  },
  profileAvatar: {
    width: 44,
    height: 44,
    borderRadius: radius.pill,
    backgroundColor: colors.primary.surface,
    borderWidth: 1.5,
    borderColor: colors.primary.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  profileAvatarText: {
    fontSize: typography.sizes.bodyLarge,
    fontWeight: typography.weights.bold,
    color: colors.primary.dark,
  },
  heroCard: {
    marginHorizontal: spacing.lg,
    marginTop: spacing.xs,
    marginBottom: spacing.base,
    backgroundColor: colors.background.card,
    borderRadius: radius.xl,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border.main,
    ...shadows.card,
  },
  balanceHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  balanceSubtext: {
    fontSize: typography.sizes.caption,
    fontWeight: typography.weights.bold,
    color: colors.text.muted,
    letterSpacing: 0.8,
  },
  balanceLoading: {
    paddingVertical: spacing.sm,
  },
  balanceRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    marginTop: spacing.xs,
  },
  balanceNumber: {
    fontSize: typography.sizes.hero,
    fontWeight: typography.weights.heavy,
    color: colors.primary.dark,
    letterSpacing: -0.5,
  },
  balanceCurrency: {
    fontSize: typography.sizes.body,
    fontWeight: typography.weights.semibold,
    color: colors.primary.main,
    marginLeft: spacing.sm,
  },
  coinBadge: {
    width: 48,
    height: 48,
    borderRadius: radius.pill,
    backgroundColor: '#FEF3C7',
    alignItems: 'center',
    justifyContent: 'center',
  },
  coinBadgeIcon: {
    fontSize: 22,
  },
  impactDivider: {
    height: 1,
    backgroundColor: colors.border.light,
    marginVertical: spacing.base,
  },
  impactRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  impactItem: {
    flex: 1,
    alignItems: 'center',
  },
  impactSeparator: {
    width: 1,
    height: 28,
    backgroundColor: colors.border.light,
  },
  impactValue: {
    fontSize: typography.sizes.bodyLarge,
    fontWeight: typography.weights.bold,
    color: colors.text.primary,
  },
  impactLabel: {
    fontSize: typography.sizes.micro,
    color: colors.text.secondary,
    marginTop: 2,
    textAlign: 'center',
  },
  primaryActionCard: {
    marginHorizontal: spacing.lg,
    marginBottom: spacing.lg,
    backgroundColor: colors.primary.main,
    borderRadius: radius.xl,
    padding: spacing.base,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    ...shadows.md,
  },
  primaryActionLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
  },
  primaryActionIconContainer: {
    width: 46,
    height: 46,
    borderRadius: radius.lg,
    backgroundColor: 'rgba(255, 255, 255, 0.2)',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: spacing.md,
  },
  primaryActionIcon: {
    fontSize: 24,
    color: '#FFFFFF',
  },
  primaryActionTextCol: {
    flex: 1,
  },
  primaryActionTitle: {
    fontSize: typography.sizes.bodyLarge,
    fontWeight: typography.weights.bold,
    color: '#FFFFFF',
  },
  primaryActionDesc: {
    fontSize: typography.sizes.caption,
    color: 'rgba(255, 255, 255, 0.9)',
    marginTop: 2,
  },
  primaryActionArrow: {
    width: 32,
    height: 32,
    borderRadius: radius.pill,
    backgroundColor: 'rgba(255, 255, 255, 0.25)',
    alignItems: 'center',
    justifyContent: 'center',
    marginLeft: spacing.sm,
  },
  primaryActionArrowText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: typography.weights.bold,
  },
  sectionHeader: {
    fontSize: typography.sizes.bodyLarge,
    fontWeight: typography.weights.bold,
    color: colors.text.primary,
    marginHorizontal: spacing.lg,
    marginBottom: spacing.md,
  },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    paddingHorizontal: spacing.lg,
    justifyContent: 'space-between',
    gap: spacing.md,
  },
  gridCard: {
    width: '47.5%',
    backgroundColor: colors.background.card,
    borderRadius: radius.lg,
    padding: spacing.base,
    borderWidth: 1,
    borderColor: colors.border.main,
    minHeight: 130,
    justifyContent: 'space-between',
    ...shadows.card,
  },
  gridIconContainer: {
    width: 40,
    height: 40,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.sm,
  },
  gridIcon: {
    fontSize: 18,
  },
  gridCardTitle: {
    fontSize: typography.sizes.body,
    fontWeight: typography.weights.bold,
    color: colors.text.primary,
    marginBottom: spacing.xxs,
  },
  gridCardSubtitle: {
    fontSize: typography.sizes.caption - 1,
    color: colors.text.secondary,
    lineHeight: 15,
  },
  pressed: {
    opacity: 0.9,
    transform: [{ scale: 0.985 }],
  },
});
