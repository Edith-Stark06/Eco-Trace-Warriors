import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { Section } from '@/components/dashboard/Section';
import { ContentCard } from '@/components/dashboard/ContentCard';
import { SkeletonCards } from '@/components/dashboard/SkeletonCards';
import { SkeletonTable } from '@/components/dashboard/SkeletonTable';
import { EmptyState } from '@/components/dashboard/EmptyState';
import { ServerError } from '@/components/common/ServerError';
import { useRecyclerHistory } from '@/features/recycler/hooks/use-recycler-assignments';
import { RecyclerHistoryKpis } from '@/features/recycler/components/RecyclerHistoryKpis';
import { RecyclerHistoryTable } from '@/features/recycler/components/RecyclerHistoryTable';
import { MaterialRecoverySummary } from '@/features/recycler/components/MaterialRecoverySummary';
import { CategoryBreakdownTable } from '@/features/recycler/components/CategoryBreakdownTable';
import {
  computeCategoryBreakdown,
  computeHistorySummary,
  computeMaterialSummary,
} from '@/features/recycler/lib/recycler-history-display';

/**
 * Recycler history & recovery analytics — a persistent view of the
 * authenticated recycler's own completed (RECYCLED) jobs, which otherwise
 * leave the active queue forever with no way to see them again. Every figure
 * is scoped to this recycler's own submissions only (GET
 * /recycler/submissions/history, authorized RECYCLER, id from the access
 * token) — never Government Analytics' national totals, never another
 * recycler's data.
 *
 * All aggregation (KPIs, recovery rate, material totals, category
 * breakdown) happens client-side over the real returned rows, mirroring the
 * same zero-extra-API-call pattern RecyclerDashboardPage already uses for
 * its status summary.
 */
export default function RecyclerHistoryPage() {
  const { data, isPending, isError, refetch } = useRecyclerHistory();

  if (isPending) {
    return (
      <div className="flex flex-col gap-8">
        <DashboardHeader
          title="Recycling history & analytics"
          description="Your facility's completed jobs and recovery efficiency."
        />
        <SkeletonCards count={4} className="lg:grid-cols-4" />
        <SkeletonTable rows={6} columns={9} />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex flex-col gap-8">
        <DashboardHeader
          title="Recycling history & analytics"
          description="Your facility's completed jobs and recovery efficiency."
        />
        <ServerError onRetry={() => void refetch()} />
      </div>
    );
  }

  const jobs = data;

  if (jobs.length === 0) {
    return (
      <div className="flex flex-col gap-8">
        <DashboardHeader
          title="Recycling history & analytics"
          description="Your facility's completed jobs and recovery efficiency."
        />
        <ContentCard>
          <EmptyState
            icon="history"
            title="No completed jobs yet"
            description="Once you complete a recycling job, it will appear here with its recovery efficiency and environmental impact — jobs no longer show up in your active queue once RECYCLED."
          />
        </ContentCard>
      </div>
    );
  }

  const summary = computeHistorySummary(jobs);
  const materialSummary = computeMaterialSummary(jobs);
  const categories = computeCategoryBreakdown(jobs);

  return (
    <div className="flex flex-col gap-8">
      <DashboardHeader
        title="Recycling history & analytics"
        description="Your facility's completed jobs and recovery efficiency."
      />

      <Section
        title="Your facility's impact"
        description="Calculated only from jobs you have personally completed — not a national or cross-facility total."
      >
        <RecyclerHistoryKpis summary={summary} />
      </Section>

      <Section
        title="Completed jobs"
        description="Every job you have recycled, newest first, with recovery % = recovered weight ÷ estimated weight × 100."
      >
        <ContentCard>
          <RecyclerHistoryTable jobs={jobs} />
        </ContentCard>
      </Section>

      <Section
        title="Material recovery"
        description="Aggregated only from materials you actually recorded at completion."
      >
        <ContentCard>
          <MaterialRecoverySummary summary={materialSummary} />
        </ContentCard>
      </Section>

      <Section title="Category breakdown" description="What you have actually processed, by category.">
        <ContentCard>
          <CategoryBreakdownTable categories={categories} />
        </ContentCard>
      </Section>
    </div>
  );
}
