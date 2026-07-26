/**
 * Government analytics data hooks.
 *
 * TanStack Query wrappers around the read-only analytics API. All four queries
 * share the central key factory and are read-only — there are no mutations,
 * because government users are observers.
 *
 * Retry policy: a 404 means the Analytics module is not deployed on this backend
 * instance (an expected "feature unavailable" condition), so we do NOT retry it
 * — the dashboard renders the dedicated informational empty state immediately.
 * Other transient failures retry with the default behaviour.
 */
import { useQuery } from '@tanstack/react-query';
import { governmentApi } from '@/api/government.api';
import { queryKeys } from '@/lib/query-keys';
import { isAnalyticsUnavailable } from '@/features/government/lib/analytics-availability';

/** Do not retry an expected 404 (module not deployed); retry others up to twice. */
function analyticsRetry(failureCount: number, error: unknown): boolean {
  if (isAnalyticsUnavailable(error)) return false;
  return failureCount < 2;
}

/** National e-waste statistics (GET /analytics/overview). */
export function useGovernmentOverview() {
  return useQuery({
    queryKey: queryKeys.government.overview,
    queryFn: () => governmentApi.getOverview(),
    retry: analyticsRetry,
  });
}

/** Regional breakdown (GET /analytics/regions). */
export function useGovernmentRegions() {
  return useQuery({
    queryKey: queryKeys.government.regions,
    queryFn: () => governmentApi.getRegions(),
    retry: analyticsRetry,
  });
}

/** National environmental impact metrics (GET /analytics/environmental-impact). */
export function useGovernmentEnvironmentalImpact() {
  return useQuery({
    queryKey: queryKeys.government.environmentalImpact,
    queryFn: () => governmentApi.getEnvironmentalImpact(),
    retry: analyticsRetry,
  });
}

/** AI demand forecast (GET /analytics/forecast). */
export function useGovernmentForecast() {
  return useQuery({
    queryKey: queryKeys.government.forecast,
    queryFn: () => governmentApi.getForecast(),
    retry: analyticsRetry,
  });
}
