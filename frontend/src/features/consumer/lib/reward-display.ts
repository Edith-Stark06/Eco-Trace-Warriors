/**
 * Reward presentation helpers.
 *
 * Pure formatting for reward figures and sustainability metrics. Units mirror
 * the backend service (`co2Unit: 'kg'`, `energyUnit: 'kWh'`, landfill in kg).
 */
import type { RewardReason } from '@/types';

/** Format an integer point/coin figure with thousands separators. */
export function formatPoints(value: number): string {
  return value.toLocaleString();
}

/** Format a metric quantity with its unit (e.g. 25 → "25 kg"). */
export function formatMetric(value: number, unit: string): string {
  return `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })} ${unit}`;
}

/** Human-readable label for a reward reason (e.g. RECYCLING → "Recycling"). */
export function rewardReasonLabel(reason: RewardReason | string): string {
  return reason.charAt(0).toUpperCase() + reason.slice(1).toLowerCase();
}
