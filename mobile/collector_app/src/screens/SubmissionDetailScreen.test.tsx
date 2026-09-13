import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react-native';
import { SubmissionDetailScreen } from './SubmissionDetailScreen';
import { submissionsApi } from '../api/submissionsApi';
import type { PublicSubmission } from '../types/submission';

jest.mock('../api/submissionsApi', () => ({
  submissionsApi: {
    get: jest.fn(),
    accept: jest.fn(),
    start: jest.fn(),
    complete: jest.fn(),
  },
}));

const getMock = submissionsApi.get as jest.Mock;
const navigate = jest.fn();
const navigation = { navigate } as never;

const baseSubmission: PublicSubmission = {
  id: 'sub-1',
  userId: 'user-1',
  category: 'Laptop',
  description: null,
  estimatedWeight: 2.5,
  address: '12 MG Road, Bengaluru',
  latitude: 12.9716,
  longitude: 77.5946,
  imageUrls: [],
  status: 'ACCEPTED',
  assignedCollectorId: 'collector-1',
  assignedRecyclerId: null,
  pickupScheduledAt: null,
  completedAt: null,
  processingStartedAt: null,
  recycledAt: null,
  recyclerNotes: null,
  recoveredWeight: null,
  materialRecovery: null,
  deviceId: null,
  ecoId: null,
  createdAt: '2026-07-20T00:00:00.000Z',
  updatedAt: '2026-07-20T00:00:00.000Z',
};

function buildRoute() {
  return { params: { submissionId: 'sub-1' } } as never;
}

describe('SubmissionDetailScreen — device registration action (P10.1)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('offers "Register device" while ACCEPTED and no device is linked yet', async () => {
    getMock.mockResolvedValue(baseSubmission);

    const { getByTestId } = await render(
      <SubmissionDetailScreen route={buildRoute()} navigation={navigation} />,
    );

    const button = await waitFor(() => getByTestId('register-device-action'));
    await fireEvent.press(button);

    expect(navigate).toHaveBeenCalledWith('Capture', { submissionId: 'sub-1' });
  });

  it('hides "Register device" once a device is already linked', async () => {
    getMock.mockResolvedValue({ ...baseSubmission, deviceId: 'DEV-2026-00000001-01' });

    const { queryByTestId, findByText } = await render(
      <SubmissionDetailScreen route={buildRoute()} navigation={navigation} />,
    );

    await findByText('DEV-2026-00000001-01');
    expect(queryByTestId('register-device-action')).toBeNull();
  });

  it('hides "Register device" before the collector has accepted the pickup', async () => {
    getMock.mockResolvedValue({ ...baseSubmission, status: 'ASSIGNED' });

    const { queryByTestId, findByText } = await render(
      <SubmissionDetailScreen route={buildRoute()} navigation={navigation} />,
    );

    await findByText('ASSIGNED');
    expect(queryByTestId('register-device-action')).toBeNull();
  });
});
