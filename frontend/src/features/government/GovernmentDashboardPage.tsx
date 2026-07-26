import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { Section } from '@/components/dashboard/Section';
import { ContentCard } from '@/components/dashboard/ContentCard';
import { SkeletonCards } from '@/components/dashboard/SkeletonCards';
import { SkeletonTable } from '@/components/dashboard/SkeletonTable';
import { EmptyState } from '@/components/dashboard/EmptyState';
import { Badge } from '@/components/ui/badge';
import {
  useGovernmentEnvironmentalImpact,
  useGovernmentForecast,
  useGovernmentOverview,
  useGovernmentRegions,
} from '@/features/government/hooks/use-government-analytics';
import { isAnalyticsUnavailable } from '@/features/government/lib/analytics-availability';
import { AnalyticsSection } from '@/features/government/components/AnalyticsSection';
import { AnalyticsUnavailable } from '@/features/government/components/AnalyticsUnavailable';
import { OverviewStats } from '@/features/government/components/OverviewStats';
import { EnvironmentalImpactStats } from '@/features/government/components/EnvironmentalImpactStats';
import { RegionalBreakdownTable } from '@/features/government/components/RegionalBreakdownTable';
import { ForecastTable } from '@/features/government/components/ForecastTable';

/**
 * Government dashboard — a READ-ONLY oversight view for observer users.
 *
 * It surfaces the four documented analytics endpoints (national overview,
 * environmental impact, regional breakdown, and AI demand forecast) as stat
 * cards and tables. There are NO write actions: government users monitor, they
 * do not edit submissions, assign collectors, run workflows, or issue rewards.
 *
 * Every figure comes straight from the backend — no client-side aggregation, no
 * mock data, no charts fabricated from unavailable data. When the Analytics
 * module is not deployed the endpoints return 404, which is treated as an
 * expected "feature unavailable" condition: if the primary overview endpoint is
 * unavailable, a single informational state is shown for the whole page;
 * otherwise each section resolves its own state independently.
 *
 * Default export for React.lazy code-splitting.
 */
export default function GovernmentDashboardPage() {
  const overview = useGovernmentOverview();
  const impact = useGovernmentEnvironmentalImpact();
  const regions = useGovernmentRegions();
  const forecast = useGovernmentForecast();

  // If the primary analytics endpoint is a confirmed 404, the Analytics module
  // is not deployed at all — show one calm, informational page-level state
  // instead of repeating it across four sections.
  const moduleUnavailable = overview.isError && isAnalyticsUnavailable(overview.error);

  return (
    <div className="flex flex-col gap-8">
      <DashboardHeader
        title="Government Dashboard"
        description="Read-only oversight of e-waste collection, recycling, recovery, and environmental impact."
        actions={<Badge variant="secondary">Observer</Badge>}
      />

      {moduleUnavailable ? (
        <Section title="Analytics">
          <ContentCard>
            <AnalyticsUnavailable />
          </ContentCard>
        </Section>
      ) : (
        <>
          <AnalyticsSection
            title="National overview"
            description="Nationwide e-waste statistics."
            query={overview}
            loading={<SkeletonCards count={4} className="lg:grid-cols-4" />}
          >
            {(data) => <OverviewStats overview={data} />}
          </AnalyticsSection>

          <AnalyticsSection
            title="Environmental impact"
            description="Estimated resources saved and landfill diverted."
            query={impact}
            loading={<SkeletonCards count={4} className="lg:grid-cols-4" />}
          >
            {(data) => <EnvironmentalImpactStats impact={data} />}
          </AnalyticsSection>

          <AnalyticsSection
            title="Regional breakdown"
            description="Per-region collection and recovery statistics."
            query={regions}
            card
            loading={<SkeletonTable rows={5} columns={7} />}
          >
            {(data) =>
              data.regions.length === 0 ? (
                <EmptyState
                  icon="government"
                  title="No regional data yet"
                  description="Regional statistics will appear here once submissions are recorded."
                />
              ) : (
                <RegionalBreakdownTable breakdown={data} />
              )
            }
          </AnalyticsSection>

          <AnalyticsSection
            title="Demand forecast"
            description="AI-projected e-waste demand, proxied from the AI service."
            query={forecast}
            card
            loading={<SkeletonTable rows={5} columns={4} />}
          >
            {(data) =>
              data.points.length === 0 ? (
                <EmptyState
                  icon="government"
                  title="No forecast available"
                  description="The AI service has not returned a demand forecast for this period."
                />
              ) : (
                <ForecastTable forecast={data} />
              )
            }
          </AnalyticsSection>
        </>
      )}
    </div>
  );
}
