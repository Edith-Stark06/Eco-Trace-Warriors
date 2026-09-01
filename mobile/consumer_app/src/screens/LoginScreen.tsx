import React, { useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { useAuth } from '../auth/AuthContext';

type Props = NativeStackScreenProps<RootStackParamList, 'Login'>;

export function LoginScreen({ navigation }: Props) {
  const { login, error, clearError } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (!email.trim() || !password) return;
    setSubmitting(true);
    clearError();
    try {
      await login(email.trim(), password);
    } catch {
      // reflected via useAuth().error
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={styles.container}>
        <Text style={styles.title} accessibilityRole="header">
          EcoTrace
        </Text>
        <Text style={styles.subtitle}>Track your e-waste, verify its journey, earn rewards</Text>

        <Text style={styles.label} nativeID="email-label">
          Email
        </Text>
        <TextInput
          style={styles.input}
          value={email}
          onChangeText={setEmail}
          autoCapitalize="none"
          keyboardType="email-address"
          textContentType="emailAddress"
          accessibilityLabelledBy="email-label"
          accessibilityLabel="Email address"
          testID="login-email-input"
        />

        <Text style={styles.label} nativeID="password-label">
          Password
        </Text>
        <TextInput
          style={styles.input}
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          textContentType="password"
          accessibilityLabelledBy="password-label"
          accessibilityLabel="Password"
          testID="login-password-input"
        />

        {error ? (
          <Text style={styles.error} accessibilityRole="alert">
            {error}
          </Text>
        ) : null}

        <Pressable
          style={[styles.button, submitting && styles.buttonDisabled]}
          onPress={handleSubmit}
          disabled={submitting}
          accessibilityRole="button"
          accessibilityLabel="Sign in"
          accessibilityState={{ disabled: submitting, busy: submitting }}
          testID="login-submit-button"
        >
          <Text style={styles.buttonText}>{submitting ? 'Signing in…' : 'Sign in'}</Text>
        </Pressable>

        <Pressable
          onPress={() => navigation.navigate('Register')}
          accessibilityRole="button"
          accessibilityLabel="Create an account"
        >
          <Text style={styles.link}>New here? Create an account</Text>
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  container: { flex: 1, justifyContent: 'center', padding: 24, backgroundColor: '#FFFFFF' },
  title: { fontSize: 28, fontWeight: '700', color: '#1B5E20', marginBottom: 4 },
  subtitle: { fontSize: 14, color: '#6B7280', marginBottom: 24 },
  label: { fontSize: 13, fontWeight: '600', color: '#374151', marginBottom: 4, marginTop: 12 },
  input: { borderWidth: 1, borderColor: '#D1D5DB', borderRadius: 8, paddingHorizontal: 12, paddingVertical: 10, fontSize: 15, minHeight: 44 },
  error: { color: '#B91C1C', marginTop: 12, fontSize: 13 },
  button: { backgroundColor: '#2E7D32', borderRadius: 8, paddingVertical: 14, alignItems: 'center', marginTop: 24, minHeight: 48 },
  buttonDisabled: { opacity: 0.6 },
  buttonText: { color: '#FFFFFF', fontSize: 16, fontWeight: '600' },
  link: { color: '#2E7D32', textAlign: 'center', marginTop: 16, fontSize: 14, fontWeight: '600' },
});
