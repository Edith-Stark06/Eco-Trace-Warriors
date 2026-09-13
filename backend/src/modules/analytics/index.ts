export { createAnalyticsService } from './analytics.service';
export type {
  AnalyticsService,
  AnalyticsServiceDeps,
  NationalOverview,
  RegionalStat,
  RegionalBreakdown,
  EnvironmentalImpact,
  DemandForecast,
  ForecastPoint,
  ForecastHistoryPoint,
  ForecastEvaluation,
  ForecastResultStatus,
} from './analytics.service';
export { createAnalyticsController } from './analytics.controller';
export type { AnalyticsController } from './analytics.controller';
export { createAnalyticsRouter } from './analytics.routes';
export type { AnalyticsRouterDeps } from './analytics.routes';
export { createAnalyticsRepository, aggregateDailyRecycledWeight } from './analytics.repository';
export type {
  AnalyticsRepository,
  SubmissionStatusCounts,
  WeightTotals,
  UserCounts,
  EnvironmentalImpactTotals,
  RegionalAggregateRow,
  DailyWeightObservation,
  RecycledWeightRow,
} from './analytics.repository';
export {
  forecastQuerySchema,
  DEFAULT_FORECAST_HORIZON,
  MAX_FORECAST_HORIZON,
} from './analytics.schemas';
export type { ForecastQuery } from './analytics.schemas';
