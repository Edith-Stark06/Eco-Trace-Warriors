import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { icons, type IconName } from '@/lib/icons';

interface StatCardProps {
  label: string;
  /** The primary figure. String so callers can pass "—" or formatted values. */
  value: string;
  /** Optional icon from the central registry, shown top-right. */
  icon?: IconName;
  /** Optional caption beneath the value (e.g. a hint or period). */
  hint?: string;
  className?: string;
}

/**
 * Compact metric tile (label + value) for dashboard summaries. Presentation
 * only — callers supply already-computed, pre-formatted values; no data
 * fetching or business logic lives here.
 */
export function StatCard({ label, value, icon, hint, className }: StatCardProps) {
  const Icon = icon ? icons[icon] : null;

  return (
    <Card className={className}>
      <CardContent className="flex items-start justify-between gap-3 p-5">
        <div className="flex flex-col gap-1">
          <span className="text-sm text-muted-foreground">{label}</span>
          <span className="text-2xl font-semibold tracking-tight">{value}</span>
          {hint && <span className="text-xs text-muted-foreground">{hint}</span>}
        </div>
        {Icon && (
          <span className={cn('rounded-md bg-muted p-2 text-muted-foreground')} aria-hidden="true">
            <Icon className="size-5" />
          </span>
        )}
      </CardContent>
    </Card>
  );
}
