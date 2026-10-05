import React from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextStyle, ViewStyle } from 'react-native';
import { colors, radius, spacing, typography } from '../../theme';

interface ButtonProps {
  label: string;
  onPress: () => void;
  variant?: 'primary' | 'secondary' | 'outline' | 'destructive' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
  loading?: boolean;
  disabled?: boolean;
  style?: ViewStyle;
  textStyle?: TextStyle;
  icon?: React.ReactNode;
  testID?: string;
  accessibilityLabel?: string;
}

export function Button({
  label,
  onPress,
  variant = 'primary',
  size = 'md',
  loading = false,
  disabled = false,
  style,
  textStyle,
  icon,
  testID,
  accessibilityLabel,
}: ButtonProps) {
  const isInteractive = !disabled && !loading;

  return (
    <Pressable
      style={({ pressed }) => [
        styles.base,
        styles[variant],
        styles[`size_${size}`],
        !isInteractive && styles.disabled,
        pressed && isInteractive && styles.pressed,
        style,
      ]}
      onPress={onPress}
      disabled={!isInteractive}
      testID={testID}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? label}
      accessibilityState={{ disabled: !isInteractive, busy: loading }}
    >
      {loading ? (
        <ActivityIndicator
          size="small"
          color={variant === 'primary' || variant === 'destructive' ? '#FFFFFF' : colors.primary.main}
        />
      ) : (
        <>
          {icon}
          <Text
            style={[
              styles.label,
              styles[`label_${variant}`],
              styles[`label_size_${size}`],
              icon ? styles.labelWithIcon : null,
              textStyle,
            ]}
          >
            {label}
          </Text>
        </>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.md,
    minHeight: 48,
  },
  primary: {
    backgroundColor: colors.primary.main,
  },
  secondary: {
    backgroundColor: colors.primary.surface,
    borderWidth: 1,
    borderColor: colors.primary.border,
  },
  outline: {
    backgroundColor: 'transparent',
    borderWidth: 1.5,
    borderColor: colors.primary.main,
  },
  destructive: {
    backgroundColor: '#DC2626',
  },
  ghost: {
    backgroundColor: 'transparent',
  },
  size_sm: {
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    minHeight: 38,
  },
  size_md: {
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    minHeight: 48,
  },
  size_lg: {
    paddingVertical: spacing.base,
    paddingHorizontal: spacing.xl,
    minHeight: 54,
  },
  label: {
    fontWeight: typography.weights.semibold,
    textAlign: 'center',
  },
  label_primary: {
    color: '#FFFFFF',
  },
  label_secondary: {
    color: colors.primary.dark,
  },
  label_outline: {
    color: colors.primary.main,
  },
  label_destructive: {
    color: '#FFFFFF',
  },
  label_ghost: {
    color: colors.primary.main,
  },
  label_size_sm: {
    fontSize: typography.sizes.body,
  },
  label_size_md: {
    fontSize: typography.sizes.bodyLarge,
  },
  label_size_lg: {
    fontSize: typography.sizes.bodyLarge + 1,
  },
  labelWithIcon: {
    marginLeft: spacing.sm,
  },
  disabled: {
    opacity: 0.5,
  },
  pressed: {
    opacity: 0.88,
    transform: [{ scale: 0.99 }],
  },
});
