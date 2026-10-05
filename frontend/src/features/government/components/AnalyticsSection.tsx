import * as React from 'react';
import type { UseQueryResult } from '@tanstack/react-query';
import { Section } from '@/components/dashboard/Section';
import { ContentCard } from '@/components/dashboard/ContentCard';
import { ServerError } from '@/components/common/ServerError';
import { AnalyticsUnavailable } from '@/features/government/components/AnalyticsUnavailable';
import { isAnalyticsUnavailable } from '@/features/government/lib/analytics-availability';

interface AnalyticsSectionProps<TData> {
  title: string;
  description?: string;
  query: UseQueryResult<TData, unknown>;
  /** Loading placeholder for this section (skeleton cards/table). */
  loading: React.ReactNode;
  /** Renders the section body once data has loaded. */
  children: (data: TData) => React.ReactNode;
  /**
   * When true, wrap the loaded body in a ContentCard (used for table sections);
   * stat-card rows pass false and render bare.
   */
  card?: boolean;
}

/**
 * Shared state machine for a single Government analytics section. Encapsulates
 * the loading / feature-unavailable (404) / server-error / data branches so the
 * page composes uniform blocks without repeating the logic four times.
 *
 * The 404 case renders the informational {@link AnalyticsUnavailable} state —
 * NOT a server error — per the product decision for undeployed analytics.
 */
export function AnalyticsSection<TData>({
  title,
  description,
  query,
  loading,
  children,
  card = false,
}: AnalyticsSectionProps<TData>) {
  const { data, isPending, isError, error, refetch } = query;

  let body: React.ReactNode;
  if (isPending) {
    body = loading;
  } else if (isError) {
    body = isAnalyticsUnavailable(error) ? (
      <AnalyticsUnavailable />
    ) : (
      <ServerError onRetry={() => void refetch()} />
    );
  } else {
    const rendered = children(data);
    body = card ? <ContentCard>{rendered}</ContentCard> : rendered;
  }

  return (
    <Section title={title} description={description}>
      {body}
    </Section>
  );
}
