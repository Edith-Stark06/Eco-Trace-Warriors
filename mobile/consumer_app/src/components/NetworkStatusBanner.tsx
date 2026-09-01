import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

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
  const label = !isOnline
    ? 'Offline — submissions will sync automatically when you reconnect'
    : failedCount > 0
      ? `${failedCount} submission(s) failed to sync — check submission history`
      : `Syncing ${pendingCount} submission(s)…`;

  return (
    <View
      style={[styles.container, !isOnline || failedCount > 0 ? styles.warning : styles.info]}
      accessibilityRole="text"
      accessibilityLiveRegion="polite"
    >
      <Text style={styles.text}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { paddingVertical: 8, paddingHorizontal: 16 },
  warning: { backgroundColor: '#FEF3C7' },
  info: { backgroundColor: '#DBEAFE' },
  text: { fontSize: 13, color: '#1F2937', textAlign: 'center' },
});
