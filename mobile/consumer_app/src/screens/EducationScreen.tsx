import React from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';

const TOPICS = [
  {
    title: 'Why e-waste recycling matters',
    body: 'Electronic waste contains recoverable materials like copper, gold, and rare earth elements, plus hazardous substances that must be handled safely rather than sent to landfill.',
  },
  {
    title: 'How EcoTrace verifies your device',
    body: 'Every device you report is photographed, AI-classified, and its lifecycle recorded. A cryptographic passport fingerprint is anchored so its recycling journey can be independently verified.',
  },
  {
    title: 'Earning GreenCoins',
    body: 'When your reported device is fully recycled by a verified recycler, GreenCoins are automatically credited to your account based on its recovered materials and environmental impact.',
  },
];

/** Static educational content — mirrors education_screen.dart. */
export function EducationScreen() {
  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {TOPICS.map((topic) => (
        <View key={topic.title} style={styles.card}>
          <Text style={styles.title} accessibilityRole="header">
            {topic.title}
          </Text>
          <Text style={styles.body}>{topic.body}</Text>
        </View>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#FFFFFF' },
  content: { padding: 16 },
  card: { backgroundColor: '#F9FAFB', borderRadius: 12, padding: 16, marginBottom: 12 },
  title: { fontSize: 16, fontWeight: '700', color: '#1B5E20', marginBottom: 8 },
  body: { fontSize: 14, color: '#374151', lineHeight: 20 },
});
