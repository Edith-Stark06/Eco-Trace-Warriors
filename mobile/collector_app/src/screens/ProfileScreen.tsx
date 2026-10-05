import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useAuth } from '../auth/AuthContext';
import { env } from '../config/env';
import { Card } from '../components/common/Card';
import { theme } from '../theme';

export function ProfileScreen() {
  const { user, logout } = useAuth();

  const initials = (user?.fullName ?? 'C')
    .split(' ')
    .map((w) => w[0])
    .join('')
    .substring(0, 2)
    .toUpperCase();

  return (
    <View style={styles.container}>
      {/* Collector Profile Card */}
      <Card variant="elevated" style={styles.profileCard}>
        <View style={styles.avatar}>
          <Text style={styles.avatarText}>{initials}</Text>
        </View>

        <Text style={styles.name}>{user?.fullName}</Text>
        <Text style={styles.email}>{user?.email}</Text>

        <View style={styles.roleBadge}>
          <View style={styles.roleDot} />
          <Text style={styles.role}>{user?.role ?? 'COLLECTOR'}</Text>
        </View>
      </Card>

      {/* Operational Stats & Details */}
      <Card variant="outlined" style={styles.detailsCard}>
        <View style={styles.detailRow}>
          <Text style={styles.detailLabel}>Operational Role</Text>
          <Text style={styles.detailValue}>Certified Field Collector</Text>
        </View>
        <View style={styles.divider} />
        <View style={styles.detailRow}>
          <Text style={styles.detailLabel}>Sync Capability</Text>
          <Text style={styles.detailValue}>Offline First (Async Queue)</Text>
        </View>
      </Card>

      {/* Sign Out Action */}
      <Pressable
        style={styles.logoutButton}
        onPress={logout}
        accessibilityRole="button"
        accessibilityLabel="Sign out"
      >
        <Text style={styles.logoutText}>Sign out</Text>
      </Pressable>

      {/* System Footer */}
      <View style={styles.footer}>
        <Text style={styles.version}>API: {env.apiBaseUrl}</Text>
        <Text style={styles.systemTag}>EcoTrace India • Collector Node</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.colors.background.app,
    padding: theme.spacing.lg,
  },
  profileCard: {
    alignItems: 'center',
    padding: theme.spacing.xl,
    marginBottom: theme.spacing.md,
  },
  avatar: {
    width: 68,
    height: 68,
    borderRadius: 34,
    backgroundColor: theme.colors.forest[100],
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: theme.spacing.md,
    borderWidth: 2,
    borderColor: theme.colors.forest[200],
  },
  avatarText: {
    fontSize: 24,
    fontWeight: theme.typography.weight.bold,
    color: theme.colors.forest[800],
  },
  name: {
    fontSize: theme.typography.size.lg,
    fontWeight: theme.typography.weight.bold,
    color: theme.colors.slate[900],
  },
  email: {
    fontSize: theme.typography.size.xs,
    color: theme.colors.slate[500],
    marginTop: 4,
  },
  roleBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: theme.colors.forest[50],
    paddingHorizontal: theme.spacing.md,
    paddingVertical: 4,
    borderRadius: theme.radius.full,
    marginTop: theme.spacing.md,
    gap: 6,
  },
  roleDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: theme.colors.forest[600],
  },
  role: {
    fontSize: 11,
    color: theme.colors.forest[800],
    fontWeight: theme.typography.weight.bold,
    letterSpacing: 0.8,
  },
  detailsCard: {
    padding: theme.spacing.md,
    marginBottom: theme.spacing.lg,
  },
  detailRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: theme.spacing.xs,
  },
  detailLabel: {
    fontSize: theme.typography.size.xs,
    color: theme.colors.slate[500],
  },
  detailValue: {
    fontSize: theme.typography.size.xs,
    fontWeight: theme.typography.weight.semibold,
    color: theme.colors.slate[800],
  },
  divider: {
    height: 1,
    backgroundColor: theme.colors.slate[100],
    marginVertical: 4,
  },
  logoutButton: {
    backgroundColor: theme.colors.rose[50],
    borderWidth: 1,
    borderColor: theme.colors.rose[200],
    borderRadius: theme.radius.md,
    paddingVertical: 14,
    alignItems: 'center',
    minHeight: 48,
  },
  logoutText: {
    color: theme.colors.rose[700],
    fontWeight: theme.typography.weight.bold,
    fontSize: theme.typography.size.sm,
  },
  footer: {
    position: 'absolute',
    bottom: theme.spacing.xl,
    left: theme.spacing.lg,
    right: theme.spacing.lg,
    alignItems: 'center',
    gap: 2,
  },
  version: {
    fontSize: 10,
    color: theme.colors.slate[400],
    fontFamily: 'monospace',
  },
  systemTag: {
    fontSize: 10,
    color: theme.colors.slate[400],
    fontWeight: theme.typography.weight.medium,
  },
});
