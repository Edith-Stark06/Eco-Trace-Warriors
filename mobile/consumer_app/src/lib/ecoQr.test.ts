import { resolveScannedCode } from './ecoQr';

describe('resolveScannedCode — EcoID QR handoff parsing (P10.4)', () => {
  it('extracts the EcoID from a valid EcoTrace QR payload', () => {
    const raw = JSON.stringify({ type: 'ECOTRACE_DEVICE', ecoId: 'ET-2026-1A2B3C4D' });
    expect(resolveScannedCode(raw)).toEqual({ kind: 'valid', identifier: 'ET-2026-1A2B3C4D' });
  });

  it('preserves plain-string identifiers for backward compatibility', () => {
    expect(resolveScannedCode('DEV-2026-ABCDEFGH-01')).toEqual({
      kind: 'valid',
      identifier: 'DEV-2026-ABCDEFGH-01',
    });
  });

  it('rejects malformed JSON', () => {
    expect(resolveScannedCode('{not valid json')).toEqual({ kind: 'invalid' });
  });

  it('rejects the wrong payload type', () => {
    const raw = JSON.stringify({ type: 'SOMETHING_ELSE', ecoId: 'ET-2026-1A2B3C4D' });
    expect(resolveScannedCode(raw)).toEqual({ kind: 'invalid' });
  });

  it('rejects a payload missing ecoId', () => {
    const raw = JSON.stringify({ type: 'ECOTRACE_DEVICE' });
    expect(resolveScannedCode(raw)).toEqual({ kind: 'invalid' });
  });

  it('rejects a payload with a blank ecoId', () => {
    const raw = JSON.stringify({ type: 'ECOTRACE_DEVICE', ecoId: '   ' });
    expect(resolveScannedCode(raw)).toEqual({ kind: 'invalid' });
  });

  it('rejects an empty scan', () => {
    expect(resolveScannedCode('   ')).toEqual({ kind: 'invalid' });
  });
});
