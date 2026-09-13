import type { DeviceRecord } from '../types/device';

/**
 * EcoID QR handoff payload (P10.4).
 *
 * The QR is a temporary digital handoff between the Collector and Consumer —
 * it carries only the public EcoID, never PII, tokens, or network addresses.
 * The Consumer app looks the EcoID up against the existing backend; nothing
 * in the QR itself is trusted as device data.
 */
export const ECOTRACE_QR_TYPE = 'ECOTRACE_DEVICE';

export interface EcoTraceQrPayload {
  type: typeof ECOTRACE_QR_TYPE;
  ecoId: string;
}

/** Builds the JSON string encoded in the handoff QR. */
export function buildEcoTraceQrPayload(ecoId: string): string {
  const payload: EcoTraceQrPayload = { type: ECOTRACE_QR_TYPE, ecoId };
  return JSON.stringify(payload);
}

/**
 * Reads the EcoID the backend already assigned at registration
 * (`POST /devices/register` — see `devices/service.py`, which stores it in
 * `record.metadata.eco_id`). Never generates a new one client-side.
 */
export function getEcoId(device: DeviceRecord): string | null {
  const value = device.metadata?.eco_id;
  return typeof value === 'string' && value.trim().length > 0 ? value : null;
}
