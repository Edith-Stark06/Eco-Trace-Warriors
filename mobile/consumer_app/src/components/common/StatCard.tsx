import React from 'react';
import { StyleSheet, Text, View, ViewStyle } from 'react-native';
import { colors, radius, spacing, typography } from '../../theme';

interface StatCardProps {
  label: string;
  value: string | number;
  unit?: string;
  icon?: string;
  sublabel?: string;
  style?: ViewStyle;
}

export function StatCard({ label, value, unit, icon, sublabel, style }: StatCardProps) {
  return (
    <View style={[styles.card, style]}>
      {icon ? <Text style={styles.icon}>{icon}</Text> : null}
      <Text style={styles.label}>{label}</Text>
      <View style={styles.valueRow}>
        <Text style={styles.value}>{value}</Text>
        {unit ? <Text style={styles.unit}>{unit}</Text> : null}
      </View>
      {sublabel ? <Text style={styles.sublabel}>{sublabel}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.background.card,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border.main,
    padding: spacing.md,
    flex: 1,
  },
  icon: {
    fontSize: 16,
    marginBottom: spacing.xxs,
  },
  label: {
    fontSize: typography.sizes.caption,
    color: colors.text.secondary,
    fontWeight: typography.weights.medium,
    marginBottom: spacing.xs,
  },
  valueRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
  },
  value: {
    fontSize: typography.sizes.subtitle,
    fontWeight: typography.weights.bold,
    color: colors.text.primary,
  },
  unit: {
    fontSize: typography.sizes.caption,
    fontWeight: typography.weights.medium,
    color: colors.text.muted,
    marginLeft: spacing.xs,
  },
  sublabel: {
    fontSize: typography.sizes.micro,
    color: colors.text.muted,
    marginTop: spacing.xxs,
  },
});
