import React, { useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { useAuth } from '../auth/AuthContext';
import { theme } from '../theme';

/** Mirrors the Flutter app's login_screen.dart: email/password against POST /auth/login. */
export function LoginScreen() {
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
      // error state is already reflected via useAuth().error
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <View style={styles.container}>
        {/* Operations Header */}
        <View style={styles.brandHeader}>
          <View style={styles.logoBadge}>
            <Text style={styles.logoIcon}>⚡</Text>
          </View>
          <Text style={styles.title} accessibilityRole="header">
            EcoTrace Collector
          </Text>
          <Text style={styles.subtitle}>Sign in to manage your assigned pickups</Text>
        </View>

        {/* Auth Form Card */}
        <View style={styles.formCard}>
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
            placeholder="collector@ecotrace.test"
            placeholderTextColor={theme.colors.slate[400]}
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
            placeholder="••••••••"
            placeholderTextColor={theme.colors.slate[400]}
            accessibilityLabelledBy="password-label"
            accessibilityLabel="Password"
            testID="login-password-input"
          />

          {error ? (
            <View style={styles.errorBox}>
              <Text style={styles.error} accessibilityRole="alert">
                {error}
              </Text>
            </View>
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
        </View>

        {/* Operations Note Footer */}
        <View style={styles.footer}>
          <Text style={styles.footerText}>Authorized Logistics Personnel Only</Text>
          <Text style={styles.systemTag}>EcoTrace India • Operations Portal</Text>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
    backgroundColor: theme.colors.background.app,
  },
  container: {
    flex: 1,
    justifyContent: 'center',
    padding: theme.spacing.xl,
  },
  brandHeader: {
    alignItems: 'center',
    marginBottom: theme.spacing.xl,
  },
  logoBadge: {
    width: 56,
    height: 56,
    borderRadius: theme.radius.lg,
    backgroundColor: theme.colors.forest[100],
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: theme.spacing.md,
  },
  logoIcon: {
    fontSize: 28,
  },
  title: {
    fontSize: theme.typography.size.xl,
    fontWeight: theme.typography.weight.bold,
    color: theme.colors.forest[800],
    letterSpacing: -0.5,
  },
  subtitle: {
    fontSize: theme.typography.size.xs,
    color: theme.colors.slate[500],
    marginTop: 6,
    textAlign: 'center',
  },
  formCard: {
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radius.lg,
    padding: theme.spacing.lg,
    borderWidth: 1,
    borderColor: theme.colors.border.main,
    ...theme.elevation.sm,
  },
  label: {
    fontSize: theme.typography.size.xs,
    fontWeight: theme.typography.weight.semibold,
    color: theme.colors.slate[700],
    marginBottom: 6,
    marginTop: theme.spacing.sm,
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
  errorBox: {
    backgroundColor: theme.colors.rose[50],
    borderRadius: theme.radius.sm,
    padding: theme.spacing.sm,
    marginTop: theme.spacing.md,
  },
  error: {
    color: theme.colors.rose[700],
    fontSize: theme.typography.size.xs,
    fontWeight: theme.typography.weight.medium,
  },
  button: {
    backgroundColor: theme.colors.forest[700],
    borderRadius: theme.radius.md,
    paddingVertical: 14,
    alignItems: 'center',
    marginTop: theme.spacing.lg,
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
  footer: {
    marginTop: theme.spacing.xxl,
    alignItems: 'center',
    gap: 2,
  },
  footerText: {
    fontSize: 11,
    color: theme.colors.slate[500],
    fontWeight: theme.typography.weight.medium,
  },
  systemTag: {
    fontSize: 10,
    color: theme.colors.slate[400],
  },
});
