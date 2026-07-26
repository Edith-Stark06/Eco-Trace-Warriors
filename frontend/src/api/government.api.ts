/**
 * Government analytics API module.
 *
 * Typed, read-only wrappers around the four analytics endpoints declared in
 * docs/engineering/05_API.md (Government + Admin scope), built on the single
 * shared Axios instance. Each method unwraps the success envelope
 * (`response.data.data`) and returns the resource directly.
 *
 * Read-only by design: government users are OBSERVERS. This module exposes NO
 * write operations — no submission edits, no assignments, no workflow
 * transitions, no reward issuance.
 *
 * Backend status: the Analytics module is documented but not yet deployed
 * (no `/analytics` router is mounted on this backend instance). Requests will
 * therefore return HTTP 404 until it ships; the hook/UI layer treats that 404
 * as an expected "feature unavailable" state rather than a server error. This
 * module makes no attempt to derive analytics from other endpoints and performs
 * no client-side aggregation.
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

  /** GET /analytics/forecast — AI demand forecast (proxied from the AI service). */
  getForecast: (): Promise<DemandForecast> =>
    unwrap<DemandForecast>(apiClient.get<ApiSuccess<DemandForecast>>('/analytics/forecast')),
};
