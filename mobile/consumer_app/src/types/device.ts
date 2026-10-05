/**
 * Mirrors intelligence/device_ai/api/device_schemas.py — the AI/passport/
 * trust lifecycle, a separate system from the backend's Submission model
 * (see docs/engineering/03_ARCHITECTURE.md, the two-system split).
 *
 * Field names below were verified directly against device_schemas.py — none
 * are guessed. Facets are exactly as the backend returns them; a facet with
 * no real data (e.g. condition not yet assessed) is still present but its
 * `status`/`value` fields say so honestly (see ConditionFacetPayload).
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

/** The real, complete set of values TrustStatusPayload.status can take (device_schemas.py). */
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
  max_age_days: number | null;
  age_days: number | null;
}

export interface DeviceTrustStatusResponse {
  success: boolean;
  trust: TrustStatusPayload;
}

/**
 * Full local + external (blockchain-abstraction ledger) trust comparison —
 * GET /devices/{id}/trust/full. `provider`/`network` reveal what actually
 * backs the "external" anchor (e.g. "memory" is an in-memory fake ledger,
 * not a live blockchain) — used so the UI never claims "Hyperledger
 * Verified" without the backend actually reporting a Fabric-backed VERIFIED
 * external status.
 */
export interface FullTrustComparisonPayload {
  device_id: string;
  local_status: string;
  external_status: string;
  overall_status: string;
  passport_fingerprint: string | null;
  local_anchored_fingerprint: string | null;
  external_anchored_fingerprint: string | null;
  local_anchor_id: string | null;
  external_anchor_id: string | null;
  transaction_id: string | null;
  provider: string;
  network: string;
  evaluated_at: string;
  reason: string;
}

export interface FullDeviceTrustStatusResponse {
  success: boolean;
  trust: FullTrustComparisonPayload;
}

// ---------------------------------------------------------------------------
// Device Passport facets (GET /devices/{identifier}/passport)
// ---------------------------------------------------------------------------

export interface DeviceIdentityFacet {
  device_id: string;
  eco_id: string | null;
  device_type: string;
  class_id: number;
  capture_id: string;
  registration_timestamp: string;
  created_at: string;
  updated_at: string;
}

export interface DetectionFacet {
  confidence: number;
  confidence_state: string;
  bounding_box: number[];
  inference_mode: string;
  model_version: string;
}

export interface BrandFacet {
  brand: string | null;
  status: string;
  source: string;
  confidence: number | null;
  raw_text: string | null;
}

export interface ConditionFacet {
  condition: string | null;
  status: string;
  source: string;
  notes: string | null;
}

export interface MaterialItem {
  material: string;
  category: string;
  mass_g: number;
  recoverable: boolean;
  hazardous: boolean;
  basis: string;
}

export interface MaterialFacet {
  materials: MaterialItem[];
  total_mass_g: number | null;
  source: string;
  version: string | null;
  notes: string | null;
}

export interface CarbonFacet {
  carbon_score: number | null;
  contributing_factors: Record<string, number>;
  methodology: string | null;
  source: string;
  version: string | null;
  notes: string | null;
}

export interface LifecycleFacet {
  current_state: string;
  is_confirmed: boolean;
  is_registered: boolean;
  is_enriched: boolean;
}

/** One real audit-trail entry — never invented; see AuditFacet.events. */
export interface DeviceAuditEvent {
  event_id: string;
  device_id: string;
  event_type:
    | 'DEVICE_DETECTED'
    | 'DEVICE_CONFIRMED'
    | 'DEVICE_REGISTERED'
    | 'DEVICE_ENRICHED'
    | 'DEVICE_EXTERNALLY_ANCHORED'
    | (string & {});
  timestamp: string;
  capture_id: string | null;
  metadata: Record<string, unknown>;
}

export interface AuditFacet {
  total_events: number;
  events: DeviceAuditEvent[];
}

export interface DevicePassportPayload {
  device_id: string;
  eco_id: string | null;
  identity: DeviceIdentityFacet;
  detection: DetectionFacet;
  brand: BrandFacet;
  condition: ConditionFacet;
  material: MaterialFacet;
  carbon: CarbonFacet;
  lifecycle: LifecycleFacet;
  audit: AuditFacet;
  generated_at: string;
}

export interface DevicePassportResponse {
  success: boolean;
  passport: DevicePassportPayload;
  request_id: string | null;
}
