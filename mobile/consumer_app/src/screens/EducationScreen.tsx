import React from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { Card } from '../components/common/Card';
import { theme } from '../theme';

const TOPICS = [
  {
    index: '01',
    icon: '⚡',
    title: 'Why e-waste recycling matters',
    body: 'Electronic waste contains recoverable materials like copper, gold, and rare earth elements, plus hazardous substances that must be handled safely rather than sent to landfill.',
  },
  {
    index: '02',
    icon: '🛡️',
    title: 'How EcoTrace verifies your device',
    body: 'Every device you report is photographed, AI-classified, and its lifecycle recorded. A cryptographic passport fingerprint is anchored so its recycling journey can be independently verified.',
  },
  {
    index: '03',
    icon: '🪙',
    title: 'Earning GreenCoins',
    body: 'When your reported device is fully recycled by a verified recycler, GreenCoins are automatically credited to your account based on its recovered materials and environmental impact.',
  },
];

/** Static educational content — mirrors education_screen.dart. */
export function EducationScreen() {
  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <View style={styles.header}>
        <Text style={styles.headerSubtitle}>ECOTRACE KNOWLEDGE BASE</Text>
        <Text style={styles.headerTitle}>Understanding Circular Electronics</Text>
      </View>

      {TOPICS.map((topic) => (
        <Card key={topic.title} variant="outlined" style={styles.card}>
          <View style={styles.cardHeader}>
            <View style={styles.iconBadge}>
              <Text style={styles.icon}>{topic.icon}</Text>
            </View>
            <Text style={styles.topicIndex}>{topic.index}</Text>
          </View>
          <Text style={styles.title} accessibilityRole="header">
            {topic.title}
          </Text>
          <Text style={styles.body}>{topic.body}</Text>
        </Card>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.colors.background.app,
  },
  content: {
    padding: theme.spacing.lg,
    paddingBottom: theme.spacing.xxl,
    gap: theme.spacing.md,
  },
  header: {
    marginBottom: theme.spacing.md,
    paddingBottom: theme.spacing.base,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.border.light,
  },
  headerSubtitle: {
    fontSize: 10,
    fontWeight: theme.typography.weight.bold,
    color: theme.colors.forest[700],
    letterSpacing: 1.2,
  },
  headerTitle: {
    fontSize: theme.typography.size.lg,
    fontWeight: theme.typography.weight.bold,
    color: theme.colors.slate[900],
    marginTop: 4,
  },
  card: {
    padding: theme.spacing.lg,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: theme.spacing.md,
  },
  iconBadge: {
    width: 36,
    height: 36,
    borderRadius: theme.radius.md,
    backgroundColor: theme.colors.forest[50],
    alignItems: 'center',
    justifyContent: 'center',
  },
  icon: {
    fontSize: 18,
  },
  topicIndex: {
    fontSize: theme.typography.size.xs,
    fontWeight: theme.typography.weight.bold,
    color: theme.colors.slate[400],
    fontFamily: 'monospace',
  },
  title: {
    fontSize: theme.typography.size.base,
    fontWeight: theme.typography.weight.bold,
    color: theme.colors.forest[900],
    marginBottom: theme.spacing.xs,
  },
  body: {
    fontSize: theme.typography.size.xs,
    color: theme.colors.slate[600],
    lineHeight: 20,
  },
});
