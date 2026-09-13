import React from 'react';
import { StyleSheet, Text, View, ViewStyle } from 'react-native';
import { colors, radius, typography } from '../../theme';

interface StatusBadgeProps {
  status: string;
  label?: string;
  style?: ViewStyle;
  size?: 'sm' | 'md';
}

/**
 * Standardized status badge for Submission, AI confidence, and Trust states.
 * Uses semantic colors with high-contrast text and accessible styling.
 */
export function StatusBadge({ status, label, style, size = 'md' }: StatusBadgeProps) {
  const norm = status.toUpperCase().replace(/\s+/g, '_');
  
  let bg: string = colors.status.neutral.bg;
  let text: string = colors.status.neutral.text;
  let border: string = colors.status.neutral.border;

  // Positive / Verified / Completed states
  if (['RECYCLED', 'COMPLETED', 'VERIFIED', 'HIGH_CONFIDENCE', 'ONLINE', 'ACTIVE'].includes(norm)) {
    bg = colors.status.success.bg;
    text = colors.status.success.text;
    border = colors.status.success.border;
  }
  // In progress / Info states
  else if (['ACCEPTED', 'IN_PROGRESS', 'COLLECTED', 'RECYCLING', 'CONFIRMED', 'REGISTERED', 'ANCHORED'].includes(norm)) {
    bg = colors.status.info.bg;
    text = colors.status.info.text;
    border = colors.status.info.border;
  }
  // Pending / Review states
  else if (['PENDING', 'ASSIGNED', 'REVIEW_REQUIRED', 'QUEUED', 'STALE'].includes(norm)) {
    bg = colors.status.warning.bg;
    text = colors.status.warning.text;
    border = colors.status.warning.border;
  }
  // Failed / Error states
  else if (['FAILED', 'REJECTED', 'MISMATCH', 'LOW_CONFIDENCE', 'ERROR', 'CONFLICT'].includes(norm)) {
    bg = colors.status.error.bg;
    text = colors.status.error.text;
    border = colors.status.error.border;
  }

  const displayText = label ?? status.replace(/_/g, ' ');

  return (
    <View
      style={[
        styles.badge,
        size === 'sm' ? styles.badgeSm : styles.badgeMd,
        { backgroundColor: bg, borderColor: border },
        style,
      ]}
      accessibilityRole="text"
      accessibilityLabel={`Status: ${displayText}`}
    >
      <View style={[styles.dot, { backgroundColor: text }]} />
      <Text style={[styles.text, size === 'sm' ? styles.textSm : styles.textMd, { color: text }]}>
        {displayText}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    borderWidth: 1,
    borderRadius: radius.pill,
  },
  badgeSm: {
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  badgeMd: {
    paddingHorizontal: 12,
    paddingVertical: 5,
  },
  dot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    marginRight: 6,
  },
  text: {
    fontWeight: typography.weights.semibold,
    textTransform: 'capitalize',
  },
  textSm: {
    fontSize: 11,
    lineHeight: 14,
  },
  textMd: {
    fontSize: 12,
    lineHeight: 16,
  },
});
