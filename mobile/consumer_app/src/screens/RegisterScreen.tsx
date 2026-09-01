import React, { useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { useAuth } from '../auth/AuthContext';

type Props = NativeStackScreenProps<RootStackParamList, 'Register'>;

/** Mirrors register.schemas.ts registerSchema — email, password, confirmPassword, fullName, phone?, region?. */
export function RegisterScreen({ navigation }: Props) {
  const { register, error, clearError } = useAuth();
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const canSubmit = fullName.trim().length >= 2 && email.trim() && password.length >= 8 && password === confirmPassword;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    clearError();
    try {
      await register({ fullName: fullName.trim(), email: email.trim(), password, confirmPassword });
    } catch {
      // reflected via useAuth().error
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.title} accessibilityRole="header">
          Create your account
        </Text>

        <Field label="Full name" value={fullName} onChangeText={setFullName} testID="register-name-input" />
        <Field
          label="Email"
          value={email}
          onChangeText={setEmail}
          autoCapitalize="none"
          keyboardType="email-address"
          testID="register-email-input"
        />
        <Field
          label="Password"
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          hint="At least 8 characters"
          testID="register-password-input"
        />
        <Field
          label="Confirm password"
          value={confirmPassword}
          onChangeText={setConfirmPassword}
          secureTextEntry
          testID="register-confirm-password-input"
        />

        {error ? (
          <Text style={styles.error} accessibilityRole="alert">
            {error}
          </Text>
        ) : null}

        <Pressable
          style={[styles.button, (!canSubmit || submitting) && styles.buttonDisabled]}
          onPress={handleSubmit}
          disabled={!canSubmit || submitting}
          accessibilityRole="button"
          accessibilityLabel="Create account"
          accessibilityState={{ disabled: !canSubmit || submitting, busy: submitting }}
          testID="register-submit-button"
        >
          <Text style={styles.buttonText}>{submitting ? 'Creating account…' : 'Create account'}</Text>
        </Pressable>

        <Pressable onPress={() => navigation.navigate('Login')} accessibilityRole="button" accessibilityLabel="Back to sign in">
          <Text style={styles.link}>Already have an account? Sign in</Text>
        </Pressable>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function Field(props: {
  label: string;
  value: string;
  onChangeText: (text: string) => void;
  secureTextEntry?: boolean;
  autoCapitalize?: 'none' | 'sentences';
  keyboardType?: 'default' | 'email-address';
  hint?: string;
  testID?: string;
}) {
  return (
    <>
      <Text style={styles.label}>{props.label}</Text>
      <TextInput
        style={styles.input}
        value={props.value}
        onChangeText={props.onChangeText}
        secureTextEntry={props.secureTextEntry}
        autoCapitalize={props.autoCapitalize}
        keyboardType={props.keyboardType}
        accessibilityLabel={props.label}
        testID={props.testID}
      />
      {props.hint ? <Text style={styles.hint}>{props.hint}</Text> : null}
    </>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  container: { padding: 24, backgroundColor: '#FFFFFF' },
  title: { fontSize: 22, fontWeight: '700', color: '#1B5E20', marginBottom: 20 },
  label: { fontSize: 13, fontWeight: '600', color: '#374151', marginBottom: 4, marginTop: 12 },
  input: { borderWidth: 1, borderColor: '#D1D5DB', borderRadius: 8, paddingHorizontal: 12, paddingVertical: 10, fontSize: 15, minHeight: 44 },
  hint: { fontSize: 12, color: '#9CA3AF', marginTop: 2 },
  error: { color: '#B91C1C', marginTop: 12, fontSize: 13 },
  button: { backgroundColor: '#2E7D32', borderRadius: 8, paddingVertical: 14, alignItems: 'center', marginTop: 24, minHeight: 48 },
  buttonDisabled: { opacity: 0.6 },
  buttonText: { color: '#FFFFFF', fontSize: 16, fontWeight: '600' },
  link: { color: '#2E7D32', textAlign: 'center', marginTop: 16, fontSize: 14, fontWeight: '600' },
});
