import { cn } from '@/lib/utils';

export interface HorizontalBarChartItem {
  /** Stable React key. */
  key: string;
  /** Row label (e.g. a region name, or a metric name). */
  label: string;
  /** Real numeric value driving the bar length. Never fabricated by this component. */
  value: number;
  /** Pre-formatted display value (with unit), rendered as text — the source of truth for the reader. */
  formattedValue: string;
}

interface HorizontalBarChartProps {
  items: HorizontalBarChartItem[];
  /** Optional accessible summary of what this chart shows. */
  ariaLabel?: string;
  className?: string;
}

/**
 * Minimal, dependency-free ranked horizontal bar chart. Bar length is
 * `value / max(values)` — a relative visual comparison only; the exact real
 * figure (with its own unit) is always printed as text next to the bar, so
 * no meaning is implied beyond what the label states. No chart library is
 * bundled in this project (see docs/engineering/07_FRONTEND.md audit,
 * P10.2's government dashboard task) — plain flexbox bars are sufficient for
 * this data volume (a handful of regions/metrics) and are trivially
 * responsive and theme-aware (colors come from the existing CSS variables).
 *
 * Presentation only: callers supply already-real, already-sorted data.
 */
export function HorizontalBarChart({ items, ariaLabel, className }: HorizontalBarChartProps) {
  const max = Math.max(1, ...items.map((item) => Math.abs(item.value)));

  return (
    <div
      className={cn('flex flex-col gap-3', className)}
      role="img"
      aria-label={ariaLabel ?? 'Bar chart'}
    >
      {items.map((item) => {
        const widthPercent = Math.max(2, (Math.abs(item.value) / max) * 100);
        return (
          <div key={item.key} className="flex flex-col gap-1">
            <div className="flex items-baseline justify-between gap-2 text-sm">
              <span className="truncate font-medium">{item.label}</span>
              <span className="shrink-0 tabular-nums text-muted-foreground">
                {item.formattedValue}
              </span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-primary transition-[width]"
                style={{ width: `${widthPercent}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
