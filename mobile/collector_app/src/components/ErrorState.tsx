import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { colors, radius, spacing, typography } from '../theme';

interface Props {
  message: string;
  onRetry?: () => void;
}

/** Color-independent error state: an icon glyph + text, never color alone (P9.8 accessibility). */
export function ErrorState({ message, onRetry }: Props) {
  return (
    <View style={styles.container} accessibilityRole="alert">
      <View style={styles.iconCircle}>
        <Text style={styles.icon} accessibilityElementsHidden importantForAccessibility="no">
          ⚠
        </Text>
      </View>
      <Text style={styles.message}>{message}</Text>
      {onRetry ? (
        <Pressable
          onPress={onRetry}
          style={({ pressed }) => [styles.button, pressed && styles.buttonPressed]}
          accessibilityRole="button"
          accessibilityLabel="Retry"
        >
          <Text style={styles.buttonText}>Retry</Text>
        </Pressable>
      ) : null}
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
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: colors.status.error.bg,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.base,
  },
  icon: {
    fontSize: 26,
    color: colors.status.error.text,
  },
  message: {
    fontSize: typography.sizes.bodyLarge,
    color: colors.text.primary,
    textAlign: 'center',
    lineHeight: typography.lineHeights.bodyLarge,
    marginBottom: spacing.xl,
    maxWidth: 320,
  },
  button: {
    backgroundColor: colors.primary.main,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.xl,
    borderRadius: radius.md,
    minHeight: 48,
    justifyContent: 'center',
    alignItems: 'center',
  },
  buttonPressed: {
    opacity: 0.88,
  },
  buttonText: {
    color: '#FFFFFF',
    fontWeight: typography.weights.semibold,
    fontSize: typography.sizes.bodyLarge,
  },
});
