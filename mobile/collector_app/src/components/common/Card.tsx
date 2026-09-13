import React from 'react';
import { Pressable, StyleSheet, View, ViewStyle } from 'react-native';
import { colors, radius, shadows, spacing } from '../../theme';

interface CardProps {
  children: React.ReactNode;
  style?: ViewStyle;
  onPress?: () => void;
  variant?: 'elevated' | 'outlined' | 'subtle' | 'brand';
  testID?: string;
  accessibilityRole?: 'button' | 'none';
  accessibilityLabel?: string;
}

export function Card({
  children,
  style,
  onPress,
  variant = 'elevated',
  testID,
  accessibilityRole,
  accessibilityLabel,
}: CardProps) {
  const cardStyle = [
    styles.base,
    variant === 'elevated' && styles.elevated,
    variant === 'outlined' && styles.outlined,
    variant === 'subtle' && styles.subtle,
    variant === 'brand' && styles.brand,
    style,
  ];

  if (onPress) {
    return (
      <Pressable
        style={({ pressed }) => [cardStyle, pressed && styles.pressed]}
        onPress={onPress}
        testID={testID}
        accessibilityRole={accessibilityRole ?? 'button'}
        accessibilityLabel={accessibilityLabel}
      >
        {children}
      </Pressable>
    );
  }

  return (
    <View style={cardStyle} testID={testID}>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  base: {
    borderRadius: radius.lg,
    padding: spacing.base,
  },
  elevated: {
    backgroundColor: colors.background.card,
    borderWidth: 1,
    borderColor: colors.border.main,
    ...shadows.card,
  },
  outlined: {
    backgroundColor: colors.background.card,
    borderWidth: 1,
    borderColor: colors.border.main,
  },
  subtle: {
    backgroundColor: colors.background.subtle,
    borderWidth: 1,
    borderColor: colors.border.light,
  },
  brand: {
    backgroundColor: colors.primary.surface,
    borderWidth: 1,
    borderColor: colors.primary.border,
  },
  pressed: {
    opacity: 0.92,
    transform: [{ scale: 0.995 }],
  },
});
