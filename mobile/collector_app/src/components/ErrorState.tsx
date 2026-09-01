import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

interface Props {
  message: string;
  onRetry?: () => void;
}

/** Color-independent error state: an icon glyph + text, never color alone (P9.8 accessibility). */
export function ErrorState({ message, onRetry }: Props) {
  return (
    <View style={styles.container} accessibilityRole="alert">
      <Text style={styles.icon} accessibilityElementsHidden importantForAccessibility="no">
        ⚠
      </Text>
      <Text style={styles.message}>{message}</Text>
      {onRetry ? (
        <Pressable
          onPress={onRetry}
          style={styles.button}
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
  container: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24 },
  icon: { fontSize: 32, marginBottom: 8 },
  message: { fontSize: 15, color: '#991B1B', textAlign: 'center', marginBottom: 16 },
  button: { backgroundColor: '#2E7D32', paddingVertical: 10, paddingHorizontal: 20, borderRadius: 8, minHeight: 44 },
  buttonText: { color: '#FFFFFF', fontWeight: '600' },
});
