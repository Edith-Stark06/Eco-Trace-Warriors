import { cn } from '@/lib/utils';

export interface TrendPoint {
  /** Opaque backend-provided period label (ISO date), used only for ordering + axis labels. */
  period: string;
  /** Real value for this period. */
  value: number;
}

interface TrendForecastChartProps {
  /** Real historical values, oldest first. */
  actual: TrendPoint[];
  /** Real predicted values, earliest first. Empty when no forecast is available — never fabricated. */
  forecast: TrendPoint[];
  /** Unit suffix for the y-axis label (e.g. "kg"). */
  unit: string;
  ariaLabel?: string;
  className?: string;
}

const WIDTH = 600;
const HEIGHT = 220;
const PAD_LEFT = 44;
const PAD_RIGHT = 12;
const PAD_TOP = 12;
const PAD_BOTTOM = 24;

function formatAxisDate(period: string): string {
  const date = new Date(period);
  if (Number.isNaN(date.getTime())) return period;
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

/**
 * Dependency-free actual-vs-forecast line/area chart. No chart library is
 * bundled in this project — a hand-built SVG is sufficient for this data
 * shape (one line, an optional continuation, at most ~180 points) and keeps
 * bundle size and dependency surface at zero.
 *
 * Draws real ACTUAL history as a solid filled line, and — only when the
 * caller actually has forecast points (never fabricated here) — continues it
 * as a dashed FORECAST line from the last actual point, with a vertical
 * "today" divider between them. The y-axis always starts at 0 (these are
 * non-negative weight series) so bar/area heights are never a misleadingly
 * zoomed-in comparison.
 */
export function TrendForecastChart({
  actual,
  forecast,
  unit,
  ariaLabel,
  className,
}: TrendForecastChartProps) {
  const all = [...actual, ...forecast];
  if (all.length === 0) {
    return null;
  }

  const maxValue = Math.max(1, ...all.map((p) => p.value));
  const plotWidth = WIDTH - PAD_LEFT - PAD_RIGHT;
  const plotHeight = HEIGHT - PAD_TOP - PAD_BOTTOM;
  const stepCount = Math.max(1, all.length - 1);

  const xAt = (index: number): number => PAD_LEFT + (index / stepCount) * plotWidth;
  const yAt = (value: number): number => PAD_TOP + plotHeight - (value / maxValue) * plotHeight;

  const actualPath = actual
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${xAt(i).toFixed(1)} ${yAt(p.value).toFixed(1)}`)
    .join(' ');

  const actualAreaPath =
    actual.length > 0
      ? `${actualPath} L ${xAt(actual.length - 1).toFixed(1)} ${(PAD_TOP + plotHeight).toFixed(1)} L ${xAt(0).toFixed(1)} ${(PAD_TOP + plotHeight).toFixed(1)} Z`
      : '';

  // Forecast continues visually from the last actual point, if any.
  const forecastStartIndex = actual.length - 1;
  const forecastPath =
    forecast.length > 0
      ? [
          actual.length > 0
            ? `M ${xAt(forecastStartIndex).toFixed(1)} ${yAt(actual[actual.length - 1].value).toFixed(1)}`
            : `M ${xAt(0).toFixed(1)} ${yAt(forecast[0].value).toFixed(1)}`,
          ...forecast.map(
            (p, i) => `L ${xAt(forecastStartIndex + 1 + i).toFixed(1)} ${yAt(p.value).toFixed(1)}`,
          ),
        ].join(' ')
      : '';

  const todayX = forecast.length > 0 && actual.length > 0 ? xAt(forecastStartIndex) : null;

  const gridLines = [0, 0.25, 0.5, 0.75, 1];

  return (
    <div className={cn('flex flex-col gap-2', className)}>
      <div className="flex items-center gap-4 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <span className="h-0.5 w-4 rounded-full bg-primary" aria-hidden="true" />
          Actual
        </span>
        {forecast.length > 0 && (
          <span className="flex items-center gap-1.5">
            <span
              className="h-0.5 w-4 rounded-full border-t-2 border-dashed border-primary/60"
              aria-hidden="true"
            />
            Forecast
          </span>
        )}
      </div>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        width="100%"
        height={HEIGHT}
        preserveAspectRatio="none"
        role="img"
        aria-label={ariaLabel ?? 'Recycled weight trend and forecast chart'}
        className="overflow-visible"
      >
        {gridLines.map((fraction) => {
          const y = PAD_TOP + plotHeight * (1 - fraction);
          return (
            <g key={fraction}>
              <line
                x1={PAD_LEFT}
                x2={WIDTH - PAD_RIGHT}
                y1={y}
                y2={y}
                stroke="var(--border)"
                strokeWidth={1}
              />
              <text x={0} y={y + 4} fontSize={10} fill="var(--muted-foreground)">
                {Math.round(maxValue * fraction).toLocaleString()}
              </text>
            </g>
          );
        })}

        {actualAreaPath && <path d={actualAreaPath} fill="var(--primary)" fillOpacity={0.12} />}
        {actualPath && (
          <path d={actualPath} fill="none" stroke="var(--primary)" strokeWidth={2} />
        )}
        {forecastPath && (
          <path
            d={forecastPath}
            fill="none"
            stroke="var(--primary)"
            strokeOpacity={0.6}
            strokeWidth={2}
            strokeDasharray="5 4"
          />
        )}

        {todayX !== null && (
          <line
            x1={todayX}
            x2={todayX}
            y1={PAD_TOP}
            y2={PAD_TOP + plotHeight}
            stroke="var(--muted-foreground)"
            strokeWidth={1}
            strokeDasharray="2 2"
          />
        )}

        <text x={PAD_LEFT} y={HEIGHT - 4} fontSize={10} fill="var(--muted-foreground)">
          {formatAxisDate(all[0].period)}
        </text>
        <text
          x={WIDTH - PAD_RIGHT}
          y={HEIGHT - 4}
          fontSize={10}
          fill="var(--muted-foreground)"
          textAnchor="end"
        >
          {formatAxisDate(all[all.length - 1].period)}
        </text>
      </svg>
      <p className="text-xs text-muted-foreground">Weight in {unit}.</p>
    </div>
  );
}
