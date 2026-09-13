import React from 'react';
import { render, waitFor } from '@testing-library/react-native';
import { DevicePassportScreen } from './DevicePassportScreen';
import { deviceAiApi } from '../api/deviceAiApi';
import { submissionsApi } from '../api/submissionsApi';
import { ApiError } from '../api/ApiError';
import type {
  DevicePassportPayload,
  DevicePassportResponse,
  DeviceTrustStatusResponse,
  FullDeviceTrustStatusResponse,
  TrustStatusPayload,
} from '../types/device';
import type { DevicePassportVerificationResponse } from '../types/verification';
import type { SubmissionLifecycleView } from '../types/submission';

// @testing-library/react-native v14 on this React 19 / test-renderer stack
// makes render() return a Promise — every render below must be awaited (see
// collector_app/src/screens/LoginScreen.test.tsx for the same note).

jest.mock('../api/deviceAiApi', () => ({
  deviceAiApi: {
    getPassport: jest.fn(),
    getTrustStatus: jest.fn(),
    verifyPassport: jest.fn(),
    getFullTrustStatus: jest.fn(),
  },
}));

jest.mock('../api/submissionsApi', () => ({
  submissionsApi: {
    getByDevice: jest.fn(),
  },
}));

const deviceAiApiMock = deviceAiApi as jest.Mocked<typeof deviceAiApi>;
const submissionsApiMock = submissionsApi as jest.Mocked<typeof submissionsApi>;

function makeLifecycle(overrides: Partial<SubmissionLifecycleView> = {}): SubmissionLifecycleView {
  return {
    submissionId: 'sub-1',
    status: 'RECYCLED',
    collectorAssigned: true,
    pickupAccepted: true,
    pickupStarted: true,
    collected: true,
    recyclingStarted: true,
    recycled: true,
    pickupStartedAt: '2026-09-05T09:00:00.000Z',
    recyclingStartedAt: '2026-09-06T09:00:00.000Z',
    recycledAt: '2026-09-07T09:00:00.000Z',
    recoveredWeight: 2.3,
    co2Saved: 62.5,
    energySaved: 37.5,
    landfillDiverted: 2.5,
    ...overrides,
  };
}

function makePassport(overrides: Partial<DevicePassportPayload> = {}): DevicePassportPayload {
  return {
    device_id: 'DEV-2026-3EDB1D84-01',
    eco_id: 'ET-2026-5ED1280B',
    identity: {
      device_id: 'DEV-2026-3EDB1D84-01',
      eco_id: 'ET-2026-5ED1280B',
      device_type: 'laptop',
      class_id: 0,
      capture_id: 'cap-f95c3edb1d84',
      registration_timestamp: '2026-09-12T12:38:41.497551+00:00',
      created_at: '2026-09-12T12:38:41.497551+00:00',
      updated_at: '2026-09-12T12:38:49.120524+00:00',
    },
    detection: {
      confidence: 0.92,
      confidence_state: 'HIGH_CONFIDENCE',
      bounding_box: [171, 23, 1051, 577],
      inference_mode: 'single_model',
      model_version: '1.0.0',
    },
    brand: { brand: null, status: 'UNKNOWN', source: 'none', confidence: null, raw_text: null },
    condition: { condition: 'UNKNOWN', status: 'UNAVAILABLE', source: 'pending_assessment', notes: null },
    material: {
      materials: [
        { material: 'Aluminium enclosure', category: 'metals', mass_g: 200, recoverable: true, hazardous: false, basis: 'device_profile' },
      ],
      total_mass_g: 200,
      source: 'device_profile',
      version: '1.0.0',
      notes: null,
    },
    carbon: {
      carbon_score: 2.5,
      contributing_factors: { metals: 2.5 },
      methodology: 'avoided_burden_co2e',
      source: 'estimated_project_model',
      version: '1.0.0',
      notes: null,
    },
    lifecycle: { current_state: 'REGISTERED', is_confirmed: true, is_registered: true, is_enriched: true },
    audit: {
      total_events: 3,
      events: [
        { event_id: 'evt-1', device_id: 'DEV-2026-3EDB1D84-01', event_type: 'DEVICE_DETECTED', timestamp: '2026-09-12T12:38:41.000000+00:00', capture_id: 'cap-1', metadata: {} },
        { event_id: 'evt-2', device_id: 'DEV-2026-3EDB1D84-01', event_type: 'DEVICE_CONFIRMED', timestamp: '2026-09-12T12:38:45.000000+00:00', capture_id: 'cap-1', metadata: {} },
        { event_id: 'evt-3', device_id: 'DEV-2026-3EDB1D84-01', event_type: 'DEVICE_REGISTERED', timestamp: '2026-09-12T12:38:49.000000+00:00', capture_id: 'cap-1', metadata: {} },
      ],
    },
    generated_at: '2026-09-12T12:40:00.000000+00:00',
    ...overrides,
  };
}

function makeTrust(overrides: Partial<TrustStatusPayload> = {}): TrustStatusPayload {
  return {
    device_id: 'DEV-2026-3EDB1D84-01',
    status: 'VERIFIED',
    passport_fingerprint: 'fp-abc',
    anchored_fingerprint: 'fp-abc',
    anchor_id: 'anc-27bb2c89e92f',
    algorithm: 'sha256',
    anchored_at: '2026-09-12T12:38:49.172906+00:00',
    evaluated_at: '2026-09-12T12:38:58.259060+00:00',
    verification_status: 'VERIFIED',
    reason: 'Passport is verified, fingerprint matches persistent trust anchor, and record is fresh.',
    is_fresh: true,
    max_age_days: 90,
    age_days: 0.0001,
    ...overrides,
  };
}

function passportResponse(passport: DevicePassportPayload): DevicePassportResponse {
  return { success: true, passport, request_id: 'req-1' };
}

function trustResponse(trust: TrustStatusPayload): DeviceTrustStatusResponse {
  return { success: true, trust };
}

function fullTrustResponse(): FullDeviceTrustStatusResponse {
  return {
    success: true,
    trust: {
      device_id: 'DEV-2026-3EDB1D84-01',
      local_status: 'VERIFIED',
      external_status: 'NOT_ANCHORED',
      overall_status: 'VERIFIED',
      passport_fingerprint: 'fp-abc',
      local_anchored_fingerprint: 'fp-abc',
      external_anchored_fingerprint: null,
      local_anchor_id: 'anc-27bb2c89e92f',
      external_anchor_id: null,
      transaction_id: null,
      provider: 'memory',
      network: 'ecotrace-channel',
      evaluated_at: '2026-09-12T12:38:58.259060+00:00',
      reason: 'Local trust verified; no external anchor exists.',
    },
  };
}

function verificationResponse(): DevicePassportVerificationResponse {
  return {
    success: true,
    verification: {
      device_id: 'DEV-2026-3EDB1D84-01',
      verification_status: 'VERIFIED',
      passport_fingerprint: 'fp-abc',
      checks: { identity: 'PASS' },
      warnings: [],
      errors: [],
      verified_at: '2026-09-12T12:38:58.000000+00:00',
    },
  };
}

function renderScreen(deviceId = 'DEV-2026-3EDB1D84-01') {
  return render(
    <DevicePassportScreen
      route={{ key: 'k', name: 'DevicePassport', params: { deviceId } }}
      navigation={{} as never}
    />,
  );
}

beforeEach(() => {
  jest.clearAllMocks();
  deviceAiApiMock.verifyPassport.mockResolvedValue(verificationResponse());
  deviceAiApiMock.getFullTrustStatus.mockResolvedValue(fullTrustResponse());
  // Default: no submission linked yet — the real, legitimate 404 case (P10.1).
  submissionsApiMock.getByDevice.mockRejectedValue(
    new ApiError('No submission is linked to this device.', { code: 'NOT_FOUND', status: 404 }),
  );
});

describe('DevicePassportScreen', () => {
  it('renders the passport when looked up by device_id', async () => {
    deviceAiApiMock.getPassport.mockResolvedValue(passportResponse(makePassport()));
    deviceAiApiMock.getTrustStatus.mockResolvedValue(trustResponse(makeTrust()));

    const { getByText } = await renderScreen();

    await waitFor(() => {
      expect(getByText('Device ID: DEV-2026-3EDB1D84-01')).toBeTruthy();
    });
    expect(deviceAiApiMock.getPassport).toHaveBeenCalledWith('DEV-2026-3EDB1D84-01');
  });

  it('renders the passport when looked up by EcoID and displays the EcoID prominently', async () => {
    deviceAiApiMock.getPassport.mockResolvedValue(passportResponse(makePassport()));
    deviceAiApiMock.getTrustStatus.mockResolvedValue(trustResponse(makeTrust()));

    const { getByText } = await renderScreen('ET-2026-5ED1280B');

    await waitFor(() => {
      expect(getByText('ET-2026-5ED1280B')).toBeTruthy();
    });
    expect(deviceAiApiMock.getPassport).toHaveBeenCalledWith('ET-2026-5ED1280B');
  });

  it('shows the EcoID label and value distinctly from the device_id', async () => {
    deviceAiApiMock.getPassport.mockResolvedValue(passportResponse(makePassport()));
    deviceAiApiMock.getTrustStatus.mockResolvedValue(trustResponse(makeTrust()));

    const { getByText } = await renderScreen();

    await waitFor(() => {
      expect(getByText('EcoID')).toBeTruthy();
      expect(getByText('ET-2026-5ED1280B')).toBeTruthy();
      expect(getByText('Device ID: DEV-2026-3EDB1D84-01')).toBeTruthy();
    });
  });

  it('shows the VERIFIED blockchain state with the real anchor ID', async () => {
    deviceAiApiMock.getPassport.mockResolvedValue(passportResponse(makePassport()));
    deviceAiApiMock.getTrustStatus.mockResolvedValue(trustResponse(makeTrust({ status: 'VERIFIED', anchor_id: 'anc-27bb2c89e92f' })));

    const { getByText } = await renderScreen();

    await waitFor(() => {
      expect(getByText('✓ Blockchain Verified')).toBeTruthy();
      expect(getByText('anc-27bb2c89e92f')).toBeTruthy();
    });
    // Never claims Hyperledger unless the backend actually says so.
    expect(() => getByText(/Hyperledger Verified/)).toThrow();
  });

  it('shows the UNANCHORED state honestly (never assumes VERIFIED just because an EcoID exists)', async () => {
    deviceAiApiMock.getPassport.mockResolvedValue(passportResponse(makePassport()));
    deviceAiApiMock.getTrustStatus.mockResolvedValue(
      trustResponse(makeTrust({ status: 'UNANCHORED', anchor_id: null, anchored_at: null })),
    );

    const { getByText } = await renderScreen();

    await waitFor(() => {
      expect(getByText('Not yet blockchain anchored')).toBeTruthy();
      expect(getByText('Not anchored')).toBeTruthy();
    });
  });

  it('shows a pending label for an anchor that exists but is not yet re-verified', async () => {
    deviceAiApiMock.getPassport.mockResolvedValue(passportResponse(makePassport()));
    deviceAiApiMock.getTrustStatus.mockResolvedValue(trustResponse(makeTrust({ status: 'ANCHORED' })));

    const { getByText } = await renderScreen();

    await waitFor(() => {
      expect(getByText('Verification pending')).toBeTruthy();
    });
  });

  it('still renders the device passport when the trust endpoint is unavailable', async () => {
    deviceAiApiMock.getPassport.mockResolvedValue(passportResponse(makePassport()));
    deviceAiApiMock.getTrustStatus.mockRejectedValue(
      new ApiError('offline', { code: 'NETWORK_ERROR', status: null }),
    );

    const { getByText } = await renderScreen();

    await waitFor(() => {
      expect(getByText('Blockchain verification unavailable')).toBeTruthy();
      // The rest of the passport still renders — the screen did not crash.
      expect(getByText('laptop')).toBeTruthy();
    });
  });

  it('shows a clean "device not found" state for an invalid identifier', async () => {
    deviceAiApiMock.getPassport.mockRejectedValue(
      new ApiError('Not found', { code: 'DEVICE_AI_ERROR', status: 404 }),
    );

    const { getByText } = await renderScreen('INVALID-DEVICE-12345');

    await waitFor(() => {
      expect(getByText('No device was found for this code.')).toBeTruthy();
    });
  });

  it('shows a clean service-unavailable state when the device intelligence backend is unreachable', async () => {
    deviceAiApiMock.getPassport.mockRejectedValue(
      new ApiError('offline', { code: 'NETWORK_ERROR', status: null }),
    );

    const { getByText } = await renderScreen();

    await waitFor(() => {
      expect(
        getByText('The device intelligence service is unavailable right now. Please try again.'),
      ).toBeTruthy();
    });
  });

  it('renders real AI intelligence information (device type, confidence, condition)', async () => {
    deviceAiApiMock.getPassport.mockResolvedValue(
      passportResponse(
        makePassport({
          identity: { ...makePassport().identity, device_type: 'laptop' },
          detection: { ...makePassport().detection, confidence: 0.92 },
        }),
      ),
    );
    deviceAiApiMock.getTrustStatus.mockResolvedValue(trustResponse(makeTrust()));

    const { getByText } = await renderScreen();

    await waitFor(() => {
      expect(getByText('laptop')).toBeTruthy();
      expect(getByText('92%')).toBeTruthy();
      // condition status is UNAVAILABLE in the fixture — must not be fabricated.
      expect(getByText('Not yet assessed')).toBeTruthy();
    });
  });

  it('renders the lifecycle timeline from real audit events only', async () => {
    deviceAiApiMock.getPassport.mockResolvedValue(passportResponse(makePassport()));
    deviceAiApiMock.getTrustStatus.mockResolvedValue(trustResponse(makeTrust()));

    const { getByText, queryByText } = await renderScreen();

    await waitFor(() => {
      expect(getByText('Detected')).toBeTruthy();
      expect(getByText('Confirmed')).toBeTruthy();
      expect(getByText('Registered')).toBeTruthy();
    });
    // No fabricated steps beyond what the backend actually returned.
    expect(queryByText('Recycled')).toBeNull();
  });

  it('shows "Information unavailable" when no audit events exist, rather than inventing history', async () => {
    deviceAiApiMock.getPassport.mockResolvedValue(
      passportResponse(makePassport({ audit: { total_events: 0, events: [] } })),
    );
    deviceAiApiMock.getTrustStatus.mockResolvedValue(trustResponse(makeTrust()));

    const { getByText } = await renderScreen();

    await waitFor(() => {
      expect(getByText('Information unavailable')).toBeTruthy();
    });
  });

  it('renders real environmental impact figures from the passport (weight + carbon)', async () => {
    deviceAiApiMock.getPassport.mockResolvedValue(
      passportResponse(
        makePassport({
          material: { ...makePassport().material, total_mass_g: 2500 },
          carbon: { ...makePassport().carbon, carbon_score: 62.5 },
        }),
      ),
    );
    deviceAiApiMock.getTrustStatus.mockResolvedValue(trustResponse(makeTrust()));

    const { getByText } = await renderScreen();

    await waitFor(() => {
      expect(getByText('2.50 kg')).toBeTruthy();
      expect(getByText('62.5 kg CO2e avoided')).toBeTruthy();
    });
  });

  describe('Collection & Recycling (P10.1 — Submission lifecycle aggregation)', () => {
    it('shows "Collection information unavailable" for a device with no linked submission', async () => {
      deviceAiApiMock.getPassport.mockResolvedValue(passportResponse(makePassport()));
      deviceAiApiMock.getTrustStatus.mockResolvedValue(trustResponse(makeTrust()));
      // beforeEach already rejects getByDevice with 404 — the legitimate unlinked state.

      const { getByText } = await renderScreen();

      await waitFor(() => {
        expect(getByText('Collection information unavailable')).toBeTruthy();
      });
    });

    it('shows real collection/recycling milestones and recovered weight for a linked submission', async () => {
      deviceAiApiMock.getPassport.mockResolvedValue(passportResponse(makePassport()));
      deviceAiApiMock.getTrustStatus.mockResolvedValue(trustResponse(makeTrust()));
      submissionsApiMock.getByDevice.mockResolvedValue(makeLifecycle());

      const { getByText } = await renderScreen();

      await waitFor(() => {
        expect(getByText('✓ Collector assigned')).toBeTruthy();
        expect(getByText('✓ Pickup completed')).toBeTruthy();
        expect(getByText('✓ Recycling completed')).toBeTruthy();
        expect(getByText('Weight recycled')).toBeTruthy();
        expect(getByText('2.3 kg')).toBeTruthy();
      });
    });

    it('shows unreached milestones honestly (no fabricated completion) for an in-flight pickup', async () => {
      deviceAiApiMock.getPassport.mockResolvedValue(passportResponse(makePassport()));
      deviceAiApiMock.getTrustStatus.mockResolvedValue(trustResponse(makeTrust()));
      submissionsApiMock.getByDevice.mockResolvedValue(
        makeLifecycle({
          status: 'IN_PROGRESS',
          collected: false,
          recyclingStarted: false,
          recycled: false,
          recycledAt: null,
          recoveredWeight: null,
          co2Saved: null,
        }),
      );

      const { getByText, queryByText } = await renderScreen();

      await waitFor(() => {
        expect(getByText('✓ Pickup accepted')).toBeTruthy();
        expect(getByText('○ Recycling completed')).toBeTruthy();
      });
      expect(queryByText('Weight recycled')).toBeNull();
    });

    it('still renders the rest of the passport when the Submission lookup fails outright', async () => {
      deviceAiApiMock.getPassport.mockResolvedValue(passportResponse(makePassport()));
      deviceAiApiMock.getTrustStatus.mockResolvedValue(trustResponse(makeTrust()));
      submissionsApiMock.getByDevice.mockRejectedValue(
        new ApiError('offline', { code: 'NETWORK_ERROR', status: null }),
      );

      const { getByText } = await renderScreen();

      await waitFor(() => {
        expect(getByText('Collection information unavailable')).toBeTruthy();
        expect(getByText('laptop')).toBeTruthy();
      });
    });
  });
});
