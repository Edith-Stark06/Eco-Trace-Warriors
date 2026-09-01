import React, { useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { submissionsApi } from '../api/submissionsApi';
import { syncQueueStorage } from '../storage/syncQueue';
import { useNetworkStatus } from '../hooks/useNetworkStatus';
import { ApiError } from '../api/ApiError';

type Props = NativeStackScreenProps<RootStackParamList, 'ReportWaste'>;

const CATEGORIES = ['laptop', 'smartphone', 'monitor', 'printer', 'battery', 'other'];

/**
 * POST /submissions (CONSUMER-only) — mirrors report_waste_screen.dart.
 * Offline-first: queued locally and synced automatically when the device
 * reconnects (useSyncManager), matching the Collector app's pattern.
 */
export function ReportWasteScreen({ navigation }: Props) {
  const isOnline = useNetworkStatus();
  const [category, setCategory] = useState(CATEGORIES[0]);
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
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.title}>
          {done === 'online' ? 'Report submitted' : 'Report queued'}
        </Text>
        <Text style={styles.body}>
          {done === 'online'
            ? 'A collector will be assigned to your pickup soon.'
            : 'You are offline — your report is saved and will submit automatically once you reconnect.'}
        </Text>
        <Pressable onPress={() => navigation.navigate('Dashboard')} accessibilityRole="button" accessibilityLabel="Back to dashboard">
          <Text style={styles.link}>Back to dashboard</Text>
        </Pressable>
      </ScrollView>
    );
  }

  return (
    <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.title} accessibilityRole="header">
          Report e-waste
        </Text>

        <Text style={styles.label}>Category</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.categoryRow}>
          {CATEGORIES.map((c) => (
            <Pressable
              key={c}
              onPress={() => setCategory(c)}
              style={[styles.categoryChip, category === c && styles.categoryChipActive]}
              accessibilityRole="button"
              accessibilityLabel={c}
              accessibilityState={{ selected: category === c }}
            >
              <Text style={[styles.categoryChipText, category === c && styles.categoryChipTextActive]}>{c}</Text>
            </Pressable>
          ))}
        </ScrollView>

        <Text style={styles.label}>Estimated weight (kg)</Text>
        <TextInput
          style={styles.input}
          value={estimatedWeight}
          onChangeText={setEstimatedWeight}
          keyboardType="numeric"
          accessibilityLabel="Estimated weight in kilograms"
        />

        <Text style={styles.label}>Pickup address</Text>
        <TextInput
          style={styles.input}
          value={address}
          onChangeText={setAddress}
          accessibilityLabel="Pickup address"
          testID="report-address-input"
        />

        <Text style={styles.label}>Description (optional)</Text>
        <TextInput
          style={[styles.input, styles.multiline]}
          value={description}
          onChangeText={setDescription}
          multiline
          accessibilityLabel="Description"
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
          accessibilityLabel="Submit report"
          accessibilityState={{ disabled: !canSubmit || submitting, busy: submitting }}
          testID="report-submit-button"
        >
          <Text style={styles.buttonText}>{submitting ? 'Submitting…' : 'Submit report'}</Text>
        </Pressable>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  container: { padding: 20, backgroundColor: '#FFFFFF' },
  title: { fontSize: 20, fontWeight: '700', color: '#1B5E20', marginBottom: 16 },
  body: { fontSize: 14, color: '#4B5563', marginBottom: 16 },
  label: { fontSize: 13, fontWeight: '600', color: '#374151', marginTop: 12, marginBottom: 6 },
  input: { borderWidth: 1, borderColor: '#D1D5DB', borderRadius: 8, paddingHorizontal: 12, paddingVertical: 10, fontSize: 15, minHeight: 44 },
  multiline: { minHeight: 80, textAlignVertical: 'top' },
  categoryRow: { flexDirection: 'row' },
  categoryChip: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: 20, borderWidth: 1, borderColor: '#D1D5DB', marginRight: 8, minHeight: 36 },
  categoryChipActive: { backgroundColor: '#2E7D32', borderColor: '#2E7D32' },
  categoryChipText: { color: '#374151', fontSize: 13 },
  categoryChipTextActive: { color: '#FFFFFF', fontWeight: '600' },
  error: { color: '#B91C1C', marginTop: 12, fontSize: 13 },
  button: { backgroundColor: '#2E7D32', borderRadius: 8, paddingVertical: 14, alignItems: 'center', marginTop: 24, minHeight: 48 },
  buttonDisabled: { opacity: 0.6 },
  buttonText: { color: '#FFFFFF', fontSize: 16, fontWeight: '600' },
  link: { color: '#2E7D32', fontWeight: '600', marginTop: 16 },
});
