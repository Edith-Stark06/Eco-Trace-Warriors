import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react-native';
import { RegisterDeviceScreen } from './RegisterDeviceScreen';
import { deviceAiApi } from '../api/deviceAiApi';
import { submissionsApi } from '../api/submissionsApi';
import * as useNetworkStatusModule from '../hooks/useNetworkStatus';
import type { DeviceRecord } from '../types/device';

jest.mock('../api/deviceAiApi', () => ({
  deviceAiApi: {
    registerDevices: jest.fn(),
    confirm: jest.fn(),
    finalize: jest.fn(),
    enrich: jest.fn(),
    anchorPassport: jest.fn(),
  },
}));

jest.mock('../api/submissionsApi', () => ({
  submissionsApi: {
    linkDevice: jest.fn(),
  },
}));

jest.mock('../hooks/useNetworkStatus', () => ({
  useNetworkStatus: jest.fn(),
}));

jest.mock('react-native-qrcode-svg', () => {
  const ReactActual = jest.requireActual('react') as typeof import('react');
  const { View } = jest.requireActual('react-native') as typeof import('react-native');
  return {
    __esModule: true,
    default: ({ value }: { value: string }) =>
      ReactActual.createElement(View, { testID: 'mock-qrcode', accessibilityLabel: value }),
  };
});

const registerDevicesMock = deviceAiApi.registerDevices as jest.Mock;
const confirmMock = deviceAiApi.confirm as jest.Mock;
const finalizeMock = deviceAiApi.finalize as jest.Mock;
const enrichMock = deviceAiApi.enrich as jest.Mock;
const anchorPassportMock = deviceAiApi.anchorPassport as jest.Mock;
const linkDeviceMock = submissionsApi.linkDevice as jest.Mock;
const useNetworkStatusMock = useNetworkStatusModule.useNetworkStatus as jest.Mock;

const device: DeviceRecord = {
  device_id: 'DEV-2026-00000001-01',
  capture_id: 'capture-1',
  class_id: 0,
  device_type: 'laptop',
  confidence: 0.95,
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

const navigation = { navigate: jest.fn(), goBack: jest.fn() } as never;
const images = [{ uri: 'file://photo.jpg', name: 'photo.jpg', type: 'image/jpeg' }];

function buildRoute(submissionId?: string) {
  return { params: { images, submissionId } } as never;
}

describe('RegisterDeviceScreen — device/submission linkage (P10.1)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    useNetworkStatusMock.mockReturnValue(true);
    registerDevicesMock.mockResolvedValue({ devices: [device] });
    confirmMock.mockResolvedValue({});
    finalizeMock.mockResolvedValue({});
    enrichMock.mockResolvedValue({});
    anchorPassportMock.mockResolvedValue({});
    linkDeviceMock.mockResolvedValue({});
  });

  it('links the device to the submission after a successful confirm, when launched from a submission', async () => {
    const { getByTestId, findByText } = await render(
      <RegisterDeviceScreen route={buildRoute('sub-123')} navigation={navigation} />,
    );

    await waitFor(() => expect(registerDevicesMock).toHaveBeenCalled());
    const confirmButton = await waitFor(() => getByTestId('register-confirm-button'));
    await fireEvent.press(confirmButton);

    await findByText('Device recorded');
    expect(linkDeviceMock).toHaveBeenCalledWith('sub-123', { deviceId: device.device_id });
  });

  it('never calls linkDevice when launched without a submission (standalone Dashboard -> Capture flow)', async () => {
    const { getByTestId, findByText } = await render(
      <RegisterDeviceScreen route={buildRoute(undefined)} navigation={navigation} />,
    );

    await waitFor(() => expect(registerDevicesMock).toHaveBeenCalled());
    const confirmButton = await waitFor(() => getByTestId('register-confirm-button'));
    await fireEvent.press(confirmButton);

    await findByText('Device recorded');
    expect(linkDeviceMock).not.toHaveBeenCalled();
  });

  it('still completes registration when linking fails (best-effort, not fabricated)', async () => {
    linkDeviceMock.mockRejectedValue(new Error('device already linked'));

    const { getByTestId, findByText } = await render(
      <RegisterDeviceScreen route={buildRoute('sub-123')} navigation={navigation} />,
    );

    await waitFor(() => expect(registerDevicesMock).toHaveBeenCalled());
    const confirmButton = await waitFor(() => getByTestId('register-confirm-button'));
    await fireEvent.press(confirmButton);

    await findByText('Device recorded');
    expect(linkDeviceMock).toHaveBeenCalled();
  });

  it('does not attempt to link while offline (link only runs on the online finalize path)', async () => {
    useNetworkStatusMock.mockReturnValue(false);

    const { getByTestId, findByText } = await render(
      <RegisterDeviceScreen route={buildRoute('sub-123')} navigation={navigation} />,
    );

    await waitFor(() => expect(registerDevicesMock).toHaveBeenCalled());
    const confirmButton = await waitFor(() => getByTestId('register-confirm-button'));
    await fireEvent.press(confirmButton);

    await findByText('Device recorded');
    expect(finalizeMock).not.toHaveBeenCalled();
    expect(linkDeviceMock).not.toHaveBeenCalled();
  });
});

describe('RegisterDeviceScreen — EcoID QR handoff (P10.4)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    useNetworkStatusMock.mockReturnValue(true);
    confirmMock.mockResolvedValue({});
    finalizeMock.mockResolvedValue({});
    enrichMock.mockResolvedValue({});
    anchorPassportMock.mockResolvedValue({});
    linkDeviceMock.mockResolvedValue({});
  });

  it('shows the EcoID QR handoff using the EcoID already returned by registration', async () => {
    registerDevicesMock.mockResolvedValue({
      devices: [{ ...device, metadata: { eco_id: 'ET-2026-1A2B3C4D' } }],
    });

    const { getByTestId, findByText } = await render(
      <RegisterDeviceScreen route={buildRoute(undefined)} navigation={navigation} />,
    );

    await waitFor(() => expect(registerDevicesMock).toHaveBeenCalled());
    const confirmButton = await waitFor(() => getByTestId('register-confirm-button'));
    await fireEvent.press(confirmButton);

    await findByText('Device recorded');
    const qr = getByTestId('mock-qrcode');
    expect(qr.props.accessibilityLabel).toBe(
      JSON.stringify({ type: 'ECOTRACE_DEVICE', ecoId: 'ET-2026-1A2B3C4D' }),
    );
    await findByText('ET-2026-1A2B3C4D');
  });

  it('never fetches or generates a second EcoID — only the registration response is used', async () => {
    registerDevicesMock.mockResolvedValue({
      devices: [{ ...device, metadata: { eco_id: 'ET-2026-1A2B3C4D' } }],
    });

    const { getByTestId, findByText } = await render(
      <RegisterDeviceScreen route={buildRoute(undefined)} navigation={navigation} />,
    );

    await waitFor(() => expect(registerDevicesMock).toHaveBeenCalled());
    const confirmButton = await waitFor(() => getByTestId('register-confirm-button'));
    await fireEvent.press(confirmButton);

    await findByText('Device recorded');
    expect(registerDevicesMock).toHaveBeenCalledTimes(1);
  });

  it('does not block a successful registration when no EcoID is present (QR display is best-effort)', async () => {
    registerDevicesMock.mockResolvedValue({ devices: [{ ...device, metadata: {} }] });

    const { getByTestId, findByText, queryByTestId } = await render(
      <RegisterDeviceScreen route={buildRoute(undefined)} navigation={navigation} />,
    );

    await waitFor(() => expect(registerDevicesMock).toHaveBeenCalled());
    const confirmButton = await waitFor(() => getByTestId('register-confirm-button'));
    await fireEvent.press(confirmButton);

    await findByText('Device recorded');
    expect(queryByTestId('ecoid-qr-block')).toBeNull();
  });
});
