import { useState, type ReactNode } from 'react';
import { Section } from '@/components/dashboard/Section';
import { ContentCard } from '@/components/dashboard/ContentCard';
import { ServerError } from '@/components/common/ServerError';
import { EmptyState } from '@/components/dashboard/EmptyState';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { TrendForecastChart } from '@/components/charts/TrendForecastChart';
import { AnalyticsUnavailable } from '@/features/government/components/AnalyticsUnavailable';
import { ForecastTable } from '@/features/government/components/ForecastTable';
import { useGovernmentForecast } from '@/features/government/hooks/use-government-analytics';
import { isAnalyticsUnavailable } from '@/features/government/lib/analytics-availability';
import { formatWeightMetric } from '@/features/government/lib/analytics-display';
import {
  DEFAULT_FORECAST_HORIZON,
  FORECAST_HORIZON_OPTIONS,
} from '@/features/government/lib/forecast-horizon';
import { icons } from '@/lib/icons';

/**
 * Recycling trend + AI forecast panel.
 *
 * This is intentionally ONE panel, not two, because the backend's only real
 * historical time series (`DemandForecast.history` — genuine daily recycled
 * weight) is embedded in the same `GET /analytics/forecast` response that
 * carries the LSTM's predicted points. A separate "Recycling Trend" section
 * fed by a different endpoint would either repeat these exact numbers under
 * a second heading or require inventing a second data source — both
 * rejected per this task's real-data rule. The chart below shows the real
 * ACTUAL history and, only when the model produced one, continues it with
 * the real FORECAST — exactly the actual-vs-forecast shape requested.
 *
 * The horizon selector always stays interactive, even when the current
 * horizon's forecast is unavailable, so the operator can try a different
 * horizon without leaving the page.
 */
export function ForecastPanel() {
  const [horizon, setHorizon] = useState(DEFAULT_FORECAST_HORIZON);
  const query = useGovernmentForecast(horizon);

  const horizonSelector = (
    <Select value={String(horizon)} onValueChange={(value) => setHorizon(Number(value))}>
      <SelectTrigger className="w-32" aria-label="Forecast horizon">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {FORECAST_HORIZON_OPTIONS.map((option) => (
          <SelectItem key={option} value={String(option)}>
            {option} days
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );

  let body: ReactNode;

  if (query.isPending) {
    body = (
      <ContentCard>
        <div className="flex flex-col gap-4">
          <Skeleton className="h-[220px] w-full" />
          <Skeleton className="h-4 w-1/3" />
        </div>
      </ContentCard>
    );
  } else if (query.isError) {
    body = (
      <ContentCard>
        {isAnalyticsUnavailable(query.error) ? (
          <AnalyticsUnavailable />
        ) : (
          <ServerError onRetry={() => void query.refetch()} />
        )}
      </ContentCard>
    );
  } else {
    const forecast = query.data;
    const hasHistory = forecast.history.length > 0;
    const actualPoints = forecast.history.map((h) => ({ period: h.period, value: h.actualWeight }));
    const forecastPoints =
      forecast.status === 'OK'
        ? forecast.points.map((p) => ({ period: p.period, value: p.predictedWeight }))
        : [];

    body = (
      <ContentCard>
        <div className="flex flex-col gap-5">
          {hasHistory ? (
            <TrendForecastChart
              actual={actualPoints}
              forecast={forecastPoints}
              unit={forecast.weightUnit}
              ariaLabel="Recycled weight: actual history and AI forecast"
            />
          ) : (
            <EmptyState
              icon="chart"
              title="No recycling history yet"
              description="A trend will appear here once recycled-weight history is recorded."
            />
          )}

          {forecast.status === 'OK' && (
            <div className="flex flex-col gap-2 border-t pt-4">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="secondary">PyTorch LSTM</Badge>
                {forecast.model && <Badge variant="outline">{forecast.model}</Badge>}
              </div>
              {forecast.evaluation && (
                <p className="text-sm text-muted-foreground">
                  Holdout evaluation — RMSE{' '}
                  {formatWeightMetric(forecast.evaluation.rmse, forecast.weightUnit)}, MAE{' '}
                  {formatWeightMetric(forecast.evaluation.mae, forecast.weightUnit)}
                  {forecast.evaluation.mape !== null
                    ? `, MAPE ${forecast.evaluation.mape.toFixed(1)}%`
                    : ''}{' '}
                  ({forecast.evaluation.trainSamples} train / {forecast.evaluation.valSamples}{' '}
                  validation windows)
                </p>
              )}
              <ForecastTable forecast={forecast} />
            </div>
          )}

          {forecast.status === 'INSUFFICIENT_HISTORICAL_DATA' && (
            <Alert>
              <icons.alert className="size-4" />
              <AlertTitle>Forecast unavailable yet</AlertTitle>
              <AlertDescription>
                {forecast.reason ??
                  `More historical recycling data is required before a reliable forecast can be ` +
                    `generated (${forecast.historyDays} of ${forecast.minHistoryDaysRequired} days available).`}
              </AlertDescription>
            </Alert>
          )}

          {(forecast.status === 'MODEL_BACKEND_UNAVAILABLE' ||
            forecast.status === 'SERVICE_UNAVAILABLE') && (
            <Alert>
              <icons.alert className="size-4" />
              <AlertTitle>Forecasting engine unavailable</AlertTitle>
              <AlertDescription>
                {forecast.reason ??
                  'The forecasting engine could not be reached. No forecast was fabricated — the rest of the dashboard remains available.'}
              </AlertDescription>
            </Alert>
          )}
        </div>
      </ContentCard>
    );
  }

  return (
    <Section
      title="Recycling trend & AI forecast"
      description="Real recycled-weight history and a PyTorch LSTM demand forecast."
      actions={horizonSelector}
    >
      {body}
    </Section>
  );
}
