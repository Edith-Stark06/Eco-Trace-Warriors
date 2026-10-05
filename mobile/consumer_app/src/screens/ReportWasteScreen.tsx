import React, { useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { submissionsApi } from '../api/submissionsApi';
import { syncQueueStorage } from '../storage/syncQueue';
import { useNetworkStatus } from '../hooks/useNetworkStatus';
import { ApiError } from '../api/ApiError';
import { Card } from '../components/common/Card';
import { Button } from '../components/common/Button';
import { colors, radius, spacing, typography } from '../theme';

type Props = NativeStackScreenProps<RootStackParamList, 'ReportWaste'>;

const CATEGORIES: { id: string; label: string; icon: string }[] = [
  { id: 'laptop', label: 'Laptop', icon: '💻' },
  { id: 'smartphone', label: 'Phone', icon: '📱' },
  { id: 'monitor', label: 'Monitor', icon: '🖥' },
  { id: 'printer', label: 'Printer', icon: '🖨' },
  { id: 'battery', label: 'Battery', icon: '🔋' },
  { id: 'other', label: 'Other', icon: '📦' },
];

/**
 * POST /submissions (CONSUMER-only).
 * Offline-first: queued locally and synced automatically when reconnecting.
 */
export function ReportWasteScreen({ navigation }: Props) {
  const isOnline = useNetworkStatus();
  const [category, setCategory] = useState(CATEGORIES[0].id);
  const [description, setDescription] = useState('');
  const [estimatedWeight, setEstimatedWeight] = useState('1');
  const [address, setAddress] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<'online' | 'queued' | null>(null);

  const canSubmit = address.trim().length > 0 && Number(estimatedWeight) > 0;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    const input = {
      category,
      description: description.trim() || undefined,
      estimatedWeight: Number(estimatedWeight),
      address: address.trim(),
      latitude: 0,
      longitude: 0,
    };
    try {
      if (isOnline) {
        await submissionsApi.create(input);
        setDone('online');
      } else {
        await syncQueueStorage.enqueue(input);
        setDone('queued');
      }
    } catch (err) {
      if (err instanceof ApiError && err.isNetworkError) {
        await syncQueueStorage.enqueue(input);
        setDone('queued');
        return;
      }
      setError(err instanceof ApiError ? err.message : 'Unable to submit your report.');
    } finally {
      setSubmitting(false);
    }
  };

  if (done) {
    return (
      <ScrollView contentContainerStyle={styles.doneContainer}>
        <View style={styles.doneCard}>
          <View style={styles.doneIconCircle}>
            <Text style={styles.doneIcon}>{done === 'online' ? '✓' : '⏳'}</Text>
          </View>
          <Text style={styles.title} accessibilityRole="header">
            {done === 'online' ? 'Report submitted' : 'Report queued'}
          </Text>
          <Text style={styles.doneBody}>
            {done === 'online'
              ? 'A collector will be assigned to your pickup soon.'
              : 'You are offline — your report is saved and will submit automatically once you reconnect.'}
          </Text>

          <Button
            label="Back to dashboard"
            onPress={() => navigation.navigate('Dashboard')}
            variant="primary"
            style={styles.doneButton}
            accessibilityLabel="Back to dashboard"
          />
        </View>
      </ScrollView>
    );
  }

  return (
    <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView style={styles.container} contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <Text style={styles.title} accessibilityRole="header">
            Report e-waste
          </Text>
          <Text style={styles.subtitle}>
            Provide details of the electronic waste item you want collected for certified recycling.
          </Text>
        </View>

        {/* Category Card */}
        <Card style={styles.formCard}>
          <Text style={styles.label}>Category</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.categoryRow}>
            {CATEGORIES.map((c) => {
              const active = category === c.id;
              return (
                <Pressable
                  key={c.id}
                  onPress={() => setCategory(c.id)}
                  style={[styles.categoryChip, active && styles.categoryChipActive]}
                  accessibilityRole="button"
                  accessibilityLabel={c.id}
                  accessibilityState={{ selected: active }}
                >
                  <Text style={styles.categoryChipIcon}>{c.icon}</Text>
                  <Text style={[styles.categoryChipText, active && styles.categoryChipTextActive]}>
                    {c.id}
                  </Text>
                </Pressable>
              );
            })}
          </ScrollView>

          {/* Weight */}
          <Text style={styles.label}>Estimated weight (kg)</Text>
          <View style={styles.weightInputContainer}>
            <TextInput
              style={styles.weightInput}
              value={estimatedWeight}
              onChangeText={setEstimatedWeight}
              keyboardType="numeric"
              placeholder="e.g. 2.5"
              placeholderTextColor={colors.text.muted}
              accessibilityLabel="Estimated weight in kilograms"
            />
            <View style={styles.weightUnitBadge}>
              <Text style={styles.weightUnitText}>KG</Text>
            </View>
          </View>
        </Card>

        {/* Location & Details Card */}
        <Card style={styles.formCard}>
          <Text style={styles.label}>Pickup address</Text>
          <TextInput
            style={styles.input}
            value={address}
            onChangeText={setAddress}
            placeholder="Complete street address, city, pin code"
            placeholderTextColor={colors.text.muted}
            accessibilityLabel="Pickup address"
            testID="report-address-input"
          />

          <Text style={styles.label}>Description (optional)</Text>
          <TextInput
            style={[styles.input, styles.multiline]}
            value={description}
            onChangeText={setDescription}
            multiline
            numberOfLines={3}
            placeholder="Working condition, accessories included, or notes for collector"
            placeholderTextColor={colors.text.muted}
            accessibilityLabel="Description"
          />
        </Card>

        {error ? (
          <View style={styles.errorContainer} accessibilityRole="alert">
            <Text style={styles.errorIcon}>⚠</Text>
            <Text style={styles.error}>{error}</Text>
          </View>
        ) : null}

        <Button
          label={submitting ? 'Submitting…' : 'Submit report'}
          onPress={handleSubmit}
          disabled={!canSubmit || submitting}
          loading={submitting}
          variant="primary"
          style={styles.submitButton}
          testID="report-submit-button"
          accessibilityLabel="Submit report"
        />
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  container: {
    flex: 1,
    backgroundColor: colors.background.app,
  },
  content: {
    padding: spacing.lg,
    paddingBottom: spacing.xxl,
  },
  header: {
    marginBottom: spacing.base,
    paddingBottom: spacing.base,
    borderBottomWidth: 1,
    borderBottomColor: colors.border.light,
  },
  title: {
    fontSize: typography.sizes.title,
    fontWeight: typography.weights.heavy,
    color: colors.text.primary,
    letterSpacing: -0.5,
  },
  subtitle: {
    fontSize: typography.sizes.body,
    color: colors.text.secondary,
    lineHeight: typography.lineHeights.body,
    marginTop: spacing.xs,
  },
  formCard: {
    marginBottom: spacing.base,
    backgroundColor: colors.background.card,
  },
  label: {
    fontSize: typography.sizes.caption,
    fontWeight: typography.weights.bold,
    color: colors.text.secondary,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginTop: spacing.sm,
    marginBottom: spacing.xs,
  },
  input: {
    borderWidth: 1,
    borderColor: colors.border.main,
    borderRadius: radius.md,
    paddingHorizontal: spacing.base,
    paddingVertical: spacing.md,
    fontSize: typography.sizes.bodyLarge,
    color: colors.text.primary,
    backgroundColor: colors.background.card,
    minHeight: 48,
  },
  multiline: {
    minHeight: 88,
    textAlignVertical: 'top',
  },
  weightInputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.border.main,
    borderRadius: radius.md,
    backgroundColor: colors.background.card,
  },
  weightInput: {
    flex: 1,
    paddingHorizontal: spacing.base,
    paddingVertical: spacing.md,
    fontSize: typography.sizes.bodyLarge,
    color: colors.text.primary,
    minHeight: 48,
  },
  weightUnitBadge: {
    backgroundColor: colors.background.subtle,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderLeftWidth: 1,
    borderLeftColor: colors.border.main,
    borderTopRightRadius: radius.md,
    borderBottomRightRadius: radius.md,
  },
  weightUnitText: {
    fontSize: typography.sizes.caption,
    fontWeight: typography.weights.bold,
    color: colors.text.muted,
  },
  categoryRow: {
    flexDirection: 'row',
    marginBottom: spacing.sm,
  },
  categoryChip: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.base,
    paddingVertical: spacing.sm + 2,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border.main,
    backgroundColor: colors.background.card,
    marginRight: spacing.sm,
    minHeight: 40,
  },
  categoryChipActive: {
    backgroundColor: colors.primary.main,
    borderColor: colors.primary.main,
  },
  categoryChipIcon: {
    fontSize: 14,
    marginRight: spacing.xs,
  },
  categoryChipText: {
    color: colors.text.secondary,
    fontSize: typography.sizes.caption,
    fontWeight: typography.weights.semibold,
  },
  categoryChipTextActive: {
    color: '#FFFFFF',
    fontWeight: typography.weights.bold,
  },
  errorContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.status.error.bg,
    borderWidth: 1,
    borderColor: colors.status.error.border,
    borderRadius: radius.md,
    padding: spacing.md,
    marginBottom: spacing.base,
  },
  errorIcon: {
    color: colors.status.error.text,
    fontSize: 16,
    marginRight: spacing.sm,
  },
  error: {
    color: colors.status.error.text,
    fontSize: typography.sizes.body,
    fontWeight: typography.weights.medium,
    flex: 1,
  },
  submitButton: {
    marginTop: spacing.sm,
  },
  doneContainer: {
    flexGrow: 1,
    justifyContent: 'center',
    padding: spacing.xl,
    backgroundColor: colors.background.app,
  },
  doneCard: {
    backgroundColor: colors.background.card,
    borderRadius: radius.xl,
    padding: spacing.xl,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.border.main,
  },
  doneIconCircle: {
    width: 64,
    height: 64,
    borderRadius: radius.pill,
    backgroundColor: colors.primary.surface,
    borderWidth: 2,
    borderColor: colors.primary.border,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.base,
  },
  doneIcon: {
    fontSize: 28,
    color: colors.primary.main,
    fontWeight: typography.weights.heavy,
  },
  doneBody: {
    fontSize: typography.sizes.bodyLarge,
    color: colors.text.secondary,
    textAlign: 'center',
    lineHeight: typography.lineHeights.bodyLarge,
    marginTop: spacing.xs,
    marginBottom: spacing.xl,
  },
  doneButton: {
    width: '100%',
  },
});
