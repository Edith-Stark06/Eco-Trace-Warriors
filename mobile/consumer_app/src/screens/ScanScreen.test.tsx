import React from 'react';
import { act, render, waitFor } from '@testing-library/react-native';
import { ScanScreen } from './ScanScreen';

interface MockBarcodeResult {
  data: string;
}

let capturedOnBarcodeScanned: ((result: MockBarcodeResult) => void) | undefined;

const mockUseCameraPermissions = jest.fn();

jest.mock('expo-camera', () => {
  const ReactActual = jest.requireActual('react') as typeof import('react');
  const { View } = jest.requireActual('react-native') as typeof import('react-native');
  return {
    __esModule: true,
    useCameraPermissions: (...args: unknown[]) => mockUseCameraPermissions(...args),
    CameraView: (props: { onBarcodeScanned?: (result: MockBarcodeResult) => void }) => {
      capturedOnBarcodeScanned = props.onBarcodeScanned;
      return ReactActual.createElement(View, { testID: 'camera-view' });
    },
  };
});

const replaceMock = jest.fn();
const navigation = { replace: replaceMock } as never;
const route = {} as never;

const INVALID_QR_MESSAGE = 'Invalid EcoTrace QR. Please scan a valid EcoTrace device QR.';

async function scan(data: string): Promise<void> {
  await act(async () => {
    capturedOnBarcodeScanned?.({ data });
  });
}

describe('ScanScreen — EcoID QR handoff (P10.4)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    capturedOnBarcodeScanned = undefined;
    mockUseCameraPermissions.mockReturnValue([{ granted: true, canAskAgain: true }, jest.fn()]);
  });

  it('extracts the EcoID from a valid EcoTrace QR and navigates to the existing Device Passport', async () => {
    await render(<ScanScreen navigation={navigation} route={route} />);
    await waitFor(() => expect(capturedOnBarcodeScanned).toBeDefined());

    await scan(JSON.stringify({ type: 'ECOTRACE_DEVICE', ecoId: 'ET-2026-1A2B3C4D' }));

    expect(replaceMock).toHaveBeenCalledWith('DevicePassport', { deviceId: 'ET-2026-1A2B3C4D' });
  });

  it('preserves plain device-ID scanning for backward compatibility', async () => {
    await render(<ScanScreen navigation={navigation} route={route} />);
    await waitFor(() => expect(capturedOnBarcodeScanned).toBeDefined());

    await scan('DEV-2026-ABCDEFGH-01');

    expect(replaceMock).toHaveBeenCalledWith('DevicePassport', {
      deviceId: 'DEV-2026-ABCDEFGH-01',
    });
  });

  it('rejects malformed QR content without navigating', async () => {
    const { findByText } = await render(<ScanScreen navigation={navigation} route={route} />);
    await waitFor(() => expect(capturedOnBarcodeScanned).toBeDefined());

    await scan('{not valid json');

    await findByText(INVALID_QR_MESSAGE);
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it('rejects a QR of the wrong type without navigating', async () => {
    const { findByText } = await render(<ScanScreen navigation={navigation} route={route} />);
    await waitFor(() => expect(capturedOnBarcodeScanned).toBeDefined());

    await scan(JSON.stringify({ type: 'SOMETHING_ELSE', ecoId: 'ET-2026-1A2B3C4D' }));

    await findByText(INVALID_QR_MESSAGE);
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it('does not crash and allows retrying after an invalid scan', async () => {
    await render(<ScanScreen navigation={navigation} route={route} />);
    await waitFor(() => expect(capturedOnBarcodeScanned).toBeDefined());

    await scan('{not valid json');
    await scan(JSON.stringify({ type: 'ECOTRACE_DEVICE', ecoId: 'ET-2026-1A2B3C4D' }));

    expect(replaceMock).toHaveBeenCalledWith('DevicePassport', { deviceId: 'ET-2026-1A2B3C4D' });
  });
});
