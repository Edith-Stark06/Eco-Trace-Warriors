import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { colors, radius, spacing, typography } from '../theme';

interface Props {
  isOnline: boolean;
  pendingCount: number;
  failedCount: number;
}

/** Status text always accompanies color — never color-only signaling (P9.8). */
export function NetworkStatusBanner({ isOnline, pendingCount, failedCount }: Props) {
  if (isOnline && pendingCount === 0 && failedCount === 0) {
    return null;
  }
  const isAlert = !isOnline || failedCount > 0;
  const label = !isOnline
    ? 'Offline — operations will sync automatically when you reconnect'
    : failedCount > 0
      ? `${failedCount} item(s) failed to sync — check submission history`
      : `Syncing ${pendingCount} item(s)…`;

  return (
    <View
      style={[styles.container, isAlert ? styles.warning : styles.info]}
      accessibilityRole="text"
      accessibilityLiveRegion="polite"
    >
      <View style={[styles.dot, isAlert ? styles.warningDot : styles.infoDot]} />
      <Text style={[styles.text, isAlert ? styles.warningText : styles.infoText]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.base,
    borderBottomWidth: 1,
  },
  warning: {
    backgroundColor: colors.status.warning.bg,
    borderBottomColor: colors.status.warning.border,
  },
  info: {
    backgroundColor: colors.status.info.bg,
    borderBottomColor: colors.status.info.border,
  },
  dot: {
    width: 6,
    height: 6,
    borderRadius: radius.pill,
    marginRight: spacing.sm,
  },
  warningDot: {
    backgroundColor: colors.status.warning.text,
  },
  infoDot: {
    backgroundColor: colors.status.info.text,
  },
  text: {
    fontSize: typography.sizes.caption,
    fontWeight: typography.weights.medium,
    textAlign: 'center',
    flexShrink: 1,
  },
  warningText: {
    color: colors.status.warning.text,
  },
  infoText: {
    color: colors.status.info.text,
  },
});
