import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { colors, radius, spacing, typography } from '../theme';

interface EmptyStateProps {
  message: string;
  icon?: string;
  subtext?: string;
}

export function EmptyState({ message, icon = '🌱', subtext }: EmptyStateProps) {
  return (
    <View style={styles.container}>
      <View style={styles.iconCircle}>
        <Text style={styles.icon} accessibilityElementsHidden importantForAccessibility="no">
          {icon}
        </Text>
      </View>
      <Text style={styles.message}>{message}</Text>
      {subtext ? <Text style={styles.subtext}>{subtext}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xl,
  },
  iconCircle: {
    width: 64,
    height: 64,
    borderRadius: radius.pill,
    backgroundColor: colors.primary.surface,
    borderWidth: 1,
    borderColor: colors.primary.border,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.base,
  },
  icon: {
    fontSize: 28,
  },
  message: {
    fontSize: typography.sizes.bodyLarge,
    fontWeight: typography.weights.semibold,
    color: colors.text.primary,
    textAlign: 'center',
    marginBottom: spacing.xs,
  },
  subtext: {
    fontSize: typography.sizes.body,
    color: colors.text.secondary,
    textAlign: 'center',
    lineHeight: typography.lineHeights.body,
    maxWidth: 280,
  },
});
