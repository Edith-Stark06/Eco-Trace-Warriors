import { buildEcoTraceQrPayload, getEcoId } from './ecoQrPayload';
import type { DeviceRecord } from '../types/device';

const baseDevice: DeviceRecord = {
  device_id: 'DEV-2026-00000001-01',
  capture_id: 'capture-1',
  class_id: 0,
  device_type: 'laptop',
  confidence: 0.92,
  confidence_state: 'HIGH_CONFIDENCE',
  bounding_box: [0, 0, 10, 10],
  model_version: 'v1',
  inference_mode: 'single_model',
  registration_state: 'DETECTED',
  condition: null,
  materials: null,
  carbon_score: null,
  metadata: {},
  created_at: '2026-09-12T00:00:00.000Z',
  updated_at: '2026-09-12T00:00:00.000Z',
};

describe('buildEcoTraceQrPayload', () => {
  it('encodes the EcoID as the canonical ECOTRACE_DEVICE payload', () => {
    const payload = buildEcoTraceQrPayload('ET-2026-1A2B3C4D');
    expect(JSON.parse(payload)).toEqual({ type: 'ECOTRACE_DEVICE', ecoId: 'ET-2026-1A2B3C4D' });
  });
});

describe('getEcoId', () => {
  it('extracts the EcoID the backend assigned at registration', () => {
    const device = { ...baseDevice, metadata: { eco_id: 'ET-2026-1A2B3C4D', image_count: 3 } };
    expect(getEcoId(device)).toBe('ET-2026-1A2B3C4D');
  });

  it('returns null when metadata has no eco_id', () => {
    expect(getEcoId({ ...baseDevice, metadata: {} })).toBeNull();
  });

  it('returns null when eco_id is not a string', () => {
    expect(getEcoId({ ...baseDevice, metadata: { eco_id: 12345 } })).toBeNull();
  });

  it('returns null for a blank eco_id', () => {
    expect(getEcoId({ ...baseDevice, metadata: { eco_id: '   ' } })).toBeNull();
  });
});
