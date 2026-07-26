import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { Section } from '@/components/dashboard/Section';
import { StatCard } from '@/components/dashboard/StatCard';
import { ContentCard } from '@/components/dashboard/ContentCard';
import { EmptyState } from '@/components/dashboard/EmptyState';
import { Badge } from '@/components/ui/badge';
import type { IconName } from '@/lib/icons';

interface RoleDashboardPlaceholderProps {
  /** Role/dashboard name shown in the header (e.g. "Consumer"). */
  title: string;
  /** Icon representing the role, reused by the empty-state block. */
  icon: IconName;
}

/**
 * Shared placeholder body for every role dashboard in this sprint.
 *
 * It contains NO business logic and NO real data — every figure is a static
 * placeholder ("—"). Its purpose is to demonstrate the shared dashboard
 * framework (header, stat row, content cards, empty state) inside the new
 * application shell. Real, role-specific content replaces this in later
 * sprints.
 */
export function RoleDashboardPlaceholder({ title, icon }: RoleDashboardPlaceholderProps) {
  return (
    <div className="flex flex-col gap-6">
      <DashboardHeader
        title={`${title} Dashboard`}
        description="Placeholder view — the dashboard framework is ready; role features arrive in a later sprint."
        actions={<Badge variant="secondary">Coming soon</Badge>}
      />

      <Section title="Overview">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="Metric one" value="—" icon={icon} hint="Awaiting data" />
          <StatCard label="Metric two" value="—" icon={icon} hint="Awaiting data" />
          <StatCard label="Metric three" value="—" icon={icon} hint="Awaiting data" />
          <StatCard label="Metric four" value="—" icon={icon} hint="Awaiting data" />
        </div>
      </Section>

      <Section title="Activity">
        <ContentCard>
          <EmptyState
            icon={icon}
            title="Nothing here yet"
            description="This section will show your activity once the feature is implemented."
          />
        </ContentCard>
      </Section>
    </div>
  );
}
