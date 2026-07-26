/**
 * Government analytics presentation helpers.
 *
 * Pure formatting for the read-only observer dashboard. Reuses the shared
 * reward/metric formatters so figures render identically across the app. No
 * data fetching, no aggregation, no business logic — the backend supplies every
 * number and these helpers only format it for display.
 */
import { formatMetric, formatPoints } from '@/features/consumer/lib/reward-display';

/** Format a whole-number count with thousands separators (e.g. 12000 → "12,000"). */
export function formatCount(value: number): string {
  return formatPoints(Math.round(value));
}

/** Format a weight quantity with its backend-provided unit (e.g. 25 → "25 kg"). */
export function formatWeightMetric(value: number, unit: string): string {
  return formatMetric(value, unit);
}

/**
 * Format a 0–1 model confidence as a percentage, or an em dash when the backend
 * did not supply one.
 */
export function formatConfidence(confidence: number | null): string {
  if (confidence === null) return '—';
  return `${Math.round(confidence * 100)}%`;
}

/**
 * Human label for an analytics `generatedAt` timestamp, or null when absent.
 * Kept null-tolerant because the provisional DTOs may evolve.
 */
export function formatGeneratedAt(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleString();
}
