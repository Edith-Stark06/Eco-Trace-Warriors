import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import type { DemandForecast } from '@/types';
import { formatWeightMetric } from '@/features/government/lib/analytics-display';

interface ForecastTableProps {
  forecast: DemandForecast;
}

/**
 * Real LSTM e-waste weight forecast (P10.1) as a table (no chart library is
 * bundled). Every value is proxied from device_ai via GET /analytics/forecast
 * and displayed as returned — no client-side modelling or interpolation.
 *
 * Recent ACTUAL history and predicted FORECAST days are shown in one
 * chronological table, each row clearly tagged, so the historical-to-forecast
 * transition is legible without a chart. No fabricated confidence interval is
 * shown — the model does not compute one.
 */
export function ForecastTable({ forecast }: ForecastTableProps) {
  const { points, history, weightUnit, model, evaluation } = forecast;

  const rows = [
    ...history.map((h) => ({ key: `actual-${h.period}`, period: h.period, weight: h.actualWeight, kind: 'ACTUAL' as const })),
    ...points.map((p) => ({ key: `forecast-${p.period}`, period: p.period, weight: p.predictedWeight, kind: 'FORECAST' as const })),
  ];

  return (
    <div className="flex flex-col gap-3">
      {(model ?? evaluation) && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
          {model && <span>Model: {model}</span>}
          {evaluation && (
            <span>
              Holdout error: RMSE {formatWeightMetric(evaluation.rmse, weightUnit)}, MAE{' '}
              {formatWeightMetric(evaluation.mae, weightUnit)}
              {evaluation.mape !== null ? `, MAPE ${evaluation.mape.toFixed(1)}%` : ''} (
              {evaluation.trainSamples} train / {evaluation.valSamples} validation windows)
            </span>
          )}
        </div>
      )}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Period</TableHead>
            <TableHead>Type</TableHead>
            <TableHead className="text-right">Weight</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.key}>
              <TableCell className="font-medium whitespace-nowrap">{row.period}</TableCell>
              <TableCell>
                <Badge variant={row.kind === 'ACTUAL' ? 'secondary' : 'default'}>
                  {row.kind === 'ACTUAL' ? 'Actual' : 'Forecast'}
                </Badge>
              </TableCell>
              <TableCell className="text-right">
                {formatWeightMetric(row.weight, weightUnit)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
