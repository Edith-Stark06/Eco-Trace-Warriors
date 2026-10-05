/**
 * EcoID QR handoff parsing (P10.4).
 *
 * The Collector app displays a temporary QR whose payload is
 * `{"type":"ECOTRACE_DEVICE","ecoId":"ET-YYYY-XXXXXXXX"}`. This module only
 * extracts the EcoID from that payload — it never trusts any other field
 * from the QR (device type, confidence, etc. all come from the backend
 * lookup that follows). A plain, non-JSON string is preserved as a raw
 * identifier for backward compatibility with any existing device/EcoID
 * code the scanner already supports.
 */
const ECOTRACE_QR_TYPE = 'ECOTRACE_DEVICE';

export type ScannedCode = { kind: 'valid'; identifier: string } | { kind: 'invalid' };

/** Parses a raw scanned string into a device/EcoID identifier, or rejects it. */
export function resolveScannedCode(raw: string): ScannedCode {
  const trimmed = raw.trim();
  if (!trimmed) {
    return { kind: 'invalid' };
  }

  // Structured EcoTrace payload: strict shape check, nothing else trusted.
  if (trimmed.startsWith('{')) {
    let parsed: unknown;
    try {
      parsed = JSON.parse(trimmed);
    } catch {
      return { kind: 'invalid' };
    }

    if (typeof parsed !== 'object' || parsed === null) {
      return { kind: 'invalid' };
    }
    const record = parsed as Record<string, unknown>;
    if (record.type !== ECOTRACE_QR_TYPE) {
      return { kind: 'invalid' };
    }
    if (typeof record.ecoId !== 'string' || record.ecoId.trim().length === 0) {
      return { kind: 'invalid' };
    }
    return { kind: 'valid', identifier: record.ecoId.trim() };
  }

  // Not JSON — preserve existing plain device-ID/EcoID scanning support.
  return { kind: 'valid', identifier: trimmed };
}
