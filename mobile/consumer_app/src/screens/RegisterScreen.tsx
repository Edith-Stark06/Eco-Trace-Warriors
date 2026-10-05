import React, { useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { useAuth } from '../auth/AuthContext';
import { theme } from '../theme';

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
        <View style={styles.header}>
          <Text style={styles.title} accessibilityRole="header">
            Create your account
          </Text>
          <Text style={styles.subtitle}>Join EcoTrace to track e-waste recycling and earn GreenCoins</Text>
        </View>

        <View style={styles.formCard}>
          <Field
            label="Full name"
            value={fullName}
            onChangeText={setFullName}
            placeholder="John Doe"
            testID="register-name-input"
          />
          <Field
            label="Email"
            value={email}
            onChangeText={setEmail}
            autoCapitalize="none"
            keyboardType="email-address"
            placeholder="john@example.com"
            testID="register-email-input"
          />
          <Field
            label="Password"
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            placeholder="••••••••"
            hint="At least 8 characters"
            testID="register-password-input"
          />
          <Field
            label="Confirm password"
            value={confirmPassword}
            onChangeText={setConfirmPassword}
            secureTextEntry
            placeholder="••••••••"
            testID="register-confirm-password-input"
          />

          {error ? (
            <View style={styles.errorBox}>
              <Text style={styles.error} accessibilityRole="alert">
                {error}
              </Text>
            </View>
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
        </View>

        <Pressable
          style={styles.footerLink}
          onPress={() => navigation.navigate('Login')}
          accessibilityRole="button"
          accessibilityLabel="Back to sign in"
        >
          <Text style={styles.link}>Already have an account? <Text style={styles.linkBold}>Sign in</Text></Text>
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
  placeholder?: string;
  testID?: string;
}) {
  return (
    <View style={styles.fieldContainer}>
      <Text style={styles.label}>{props.label}</Text>
      <TextInput
        style={styles.input}
        value={props.value}
        onChangeText={props.onChangeText}
        secureTextEntry={props.secureTextEntry}
        autoCapitalize={props.autoCapitalize}
        keyboardType={props.keyboardType}
        placeholder={props.placeholder}
        placeholderTextColor={theme.colors.slate[400]}
        accessibilityLabel={props.label}
        testID={props.testID}
      />
      {props.hint ? <Text style={styles.hint}>{props.hint}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
    backgroundColor: theme.colors.background.app,
  },
  container: {
    padding: theme.spacing.xl,
    paddingTop: theme.spacing.xxl,
    paddingBottom: theme.spacing.xxl,
  },
  header: {
    marginBottom: theme.spacing.xl,
    paddingBottom: theme.spacing.base,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.border.light,
  },
  title: {
    fontSize: theme.typography.size.xl,
    fontWeight: theme.typography.weight.bold,
    color: theme.colors.forest[800],
  },
  subtitle: {
    fontSize: theme.typography.size.xs,
    color: theme.colors.slate[500],
    marginTop: 4,
    lineHeight: 18,
  },
  formCard: {
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radius.lg,
    padding: theme.spacing.lg,
    borderWidth: 1,
    borderColor: theme.colors.border.main,
    ...theme.elevation.sm,
  },
  fieldContainer: {
    marginBottom: theme.spacing.md,
  },
  label: {
    fontSize: theme.typography.size.xs,
    fontWeight: theme.typography.weight.semibold,
    color: theme.colors.slate[700],
    marginBottom: 6,
  },
  input: {
    borderWidth: 1,
    borderColor: theme.colors.border.main,
    borderRadius: theme.radius.md,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: 12,
    fontSize: theme.typography.size.sm,
    color: theme.colors.slate[900],
    backgroundColor: theme.colors.surface,
    minHeight: 48,
  },
  hint: {
    fontSize: 11,
    color: theme.colors.slate[400],
    marginTop: 4,
  },
  errorBox: {
    backgroundColor: theme.colors.rose[50],
    borderRadius: theme.radius.sm,
    padding: theme.spacing.sm,
    marginBottom: theme.spacing.sm,
  },
  error: {
    color: theme.colors.rose[700],
    fontSize: theme.typography.size.xs,
    fontWeight: theme.typography.weight.medium,
  },
  button: {
    backgroundColor: theme.colors.forest[600],
    borderRadius: theme.radius.md,
    paddingVertical: 14,
    alignItems: 'center',
    marginTop: theme.spacing.md,
    minHeight: 48,
    ...theme.elevation.xs,
  },
  buttonDisabled: {
    opacity: 0.6,
  },
  buttonText: {
    color: '#FFFFFF',
    fontSize: theme.typography.size.sm,
    fontWeight: theme.typography.weight.bold,
  },
  footerLink: {
    marginTop: theme.spacing.xl,
    alignItems: 'center',
    paddingVertical: theme.spacing.sm,
  },
  link: {
    color: theme.colors.slate[600],
    fontSize: theme.typography.size.xs,
  },
  linkBold: {
    color: theme.colors.forest[700],
    fontWeight: theme.typography.weight.bold,
  },
});
