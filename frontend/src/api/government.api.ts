/**
 * Government analytics API module.
 *
 * Typed, read-only wrappers around the analytics endpoints declared in
 * docs/engineering/05_API.md (Government + Admin scope) and implemented in
 * backend/src/modules/analytics/, built on the single shared Axios instance.
 * Each method unwraps the success envelope (`response.data.data`) and
 * returns the resource directly.
 *
 * Read-only by design: government users are OBSERVERS. This module exposes NO
 * write operations — no submission edits, no assignments, no workflow
 * transitions, no reward issuance.
 *
 * Backend status (P10.2): all four endpoints are implemented and deployed,
 * restricted server-side to GOVERNMENT/ADMIN. `/analytics/forecast` proxies a
 * real, trained PyTorch LSTM (`intelligence/device_ai/forecasting/`) — its
 * `horizon` query param (1–90 days) is forwarded as-is; the backend never
 * fabricates a prediction, degrading honestly via `status`/`reason` instead
 * (see `ForecastResultStatus`). If the Analytics module is ever undeployed on
 * a given backend instance, these calls 404 and the hook/UI layer treats that
 * as an expected "feature unavailable" state rather than a server error. This
 * module makes no attempt to derive analytics from other endpoints and
 * performs no client-side aggregation.
 */
import { apiClient } from '@/api/axios';
import { unwrap } from '@/api/client';
import type {
  ApiSuccess,
  DemandForecast,
  EnvironmentalImpact,
  NationalOverview,
  RegionalBreakdown,
} from '@/types';

export const governmentApi = {
  /** GET /analytics/overview — national e-waste statistics. */
  getOverview: (): Promise<NationalOverview> =>
    unwrap<NationalOverview>(apiClient.get<ApiSuccess<NationalOverview>>('/analytics/overview')),

  /** GET /analytics/regions — regional breakdown / heatmap data. */
  getRegions: (): Promise<RegionalBreakdown> =>
    unwrap<RegionalBreakdown>(apiClient.get<ApiSuccess<RegionalBreakdown>>('/analytics/regions')),

  /** GET /analytics/environmental-impact — national impact metrics. */
  getEnvironmentalImpact: (): Promise<EnvironmentalImpact> =>
    unwrap<EnvironmentalImpact>(
      apiClient.get<ApiSuccess<EnvironmentalImpact>>('/analytics/environmental-impact'),
    ),

  /**
   * GET /analytics/forecast?horizon= — real LSTM e-waste weight forecast.
   * `horizon` is the number of days to predict (backend-validated 1–90,
   * default 30 when omitted).
   */
  getForecast: (horizon?: number): Promise<DemandForecast> =>
    unwrap<DemandForecast>(
      apiClient.get<ApiSuccess<DemandForecast>>('/analytics/forecast', {
        params: horizon !== undefined ? { horizon } : undefined,
      }),
    ),
};
