import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useAuth } from '../auth/AuthContext';
import { env } from '../config/env';

export function ProfileScreen() {
  const { user, logout } = useAuth();

  return (
    <View style={styles.container}>
      <Text style={styles.name}>{user?.fullName}</Text>
      <Text style={styles.email}>{user?.email}</Text>
      {user?.region ? <Text style={styles.region}>{user.region}</Text> : null}

      <Pressable style={styles.logoutButton} onPress={logout} accessibilityRole="button" accessibilityLabel="Sign out">
        <Text style={styles.logoutText}>Sign out</Text>
      </Pressable>

      <Text style={styles.version}>API: {env.apiBaseUrl}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#FFFFFF', padding: 24 },
  name: { fontSize: 20, fontWeight: '700', color: '#111827' },
  email: { fontSize: 14, color: '#6B7280', marginTop: 4 },
  region: { fontSize: 13, color: '#2E7D32', marginTop: 4 },
  logoutButton: { marginTop: 24, backgroundColor: '#B91C1C', borderRadius: 8, paddingVertical: 12, alignItems: 'center', minHeight: 44 },
  logoutText: { color: '#FFFFFF', fontWeight: '600' },
  version: { position: 'absolute', bottom: 24, left: 24, fontSize: 11, color: '#9CA3AF' },
});
