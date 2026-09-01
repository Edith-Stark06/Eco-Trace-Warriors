/**
 * Mirrors intelligence/device_ai/api/device_schemas.py — the AI/passport/
 * trust lifecycle, a separate system from the backend's Submission model
 * (see docs/engineering/03_ARCHITECTURE.md, the two-system split).
 */
export interface DeviceRecord {
  device_id: string;
  capture_id: string;
  class_id: number;
  device_type: string;
  confidence: number;
  confidence_state: 'HIGH_CONFIDENCE' | 'REVIEW_REQUIRED' | 'LOW_CONFIDENCE';
  bounding_box: [number, number, number, number];
  model_version: string;
  inference_mode: string;
  registration_state: 'DETECTED' | 'CONFIRMED' | 'REGISTERED';
  condition: string | null;
  materials: Record<string, number> | null;
  carbon_score: number | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface DeviceRegistrationResponse {
  success: boolean;
  capture_id: string;
  total_detected: number;
  devices: DeviceRecord[];
  inference_mode: string;
  request_id: string | null;
}

export interface DeviceStateUpdateResponse {
  success: boolean;
  device: DeviceRecord;
  previous_state: string;
  current_state: string;
}

export type TrustStatus = 'UNANCHORED' | 'ANCHORED' | 'VERIFIED' | 'MISMATCH' | 'STALE';

export interface TrustStatusPayload {
  device_id: string;
  status: TrustStatus;
  passport_fingerprint: string | null;
  anchored_fingerprint: string | null;
  anchor_id: string | null;
  algorithm: string;
  anchored_at: string | null;
  evaluated_at: string;
  verification_status: 'VERIFIED' | 'WARNING' | 'INVALID' | null;
  reason: string;
  is_fresh: boolean;
}

export interface DeviceTrustStatusResponse {
  success: boolean;
  trust: TrustStatusPayload;
}

/** Loosely-typed passport payload — full facet-by-facet typing is deferred; the
 *  UI only reads a handful of top-level fields plus `lifecycle.state`. */
export interface DevicePassportPayload {
  device_id: string;
  eco_id: string | null;
  lifecycle: { state?: string; [key: string]: unknown };
  generated_at: string;
  [key: string]: unknown;
}

export interface DevicePassportResponse {
  success: boolean;
  passport: DevicePassportPayload;
}
