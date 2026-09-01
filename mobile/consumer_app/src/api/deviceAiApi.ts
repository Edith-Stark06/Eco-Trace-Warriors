import { env } from '../config/env';
import { ApiError } from './ApiError';
import type { DevicePassportResponse, DeviceTrustStatusResponse } from '../types/device';
import type { DevicePassportVerificationResponse } from '../types/verification';

/**
 * Consumer-side, read-only device_ai calls. Per the architecture rule
 * (mobile never talks to Fabric directly — see
 * docs/engineering/09_BLOCKCHAIN.md), all blockchain trust evidence is
 * read through device_ai's REST API, which owns the real
 * FabricGatewayClient (P9.2) — this app never touches a peer, wallet, or
 * private key.
 */
const SERVICE_API_KEY = process.env.EXPO_PUBLIC_DEVICE_AI_SERVICE_API_KEY;

async function deviceAiGet<T>(path: string): Promise<T> {
  const headers: Record<string, string> = {};
  if (SERVICE_API_KEY) {
    headers['X-Service-Api-Key'] = SERVICE_API_KEY;
  }
  let response: Response;
  try {
    response = await fetch(`${env.deviceAiBaseUrl}${path}`, { headers });
  } catch {
    throw new ApiError('Unable to reach the device intelligence service.', {
      code: 'NETWORK_ERROR',
      status: null,
    });
  }
  const json = await response.json().catch(() => null);
  if (!response.ok || !json) {
    throw new ApiError(json?.detail ?? `Device lookup failed (${response.status}).`, {
      code: 'DEVICE_AI_ERROR',
      status: response.status,
    });
  }
  return json as T;
}

export const deviceAiApi = {
  getPassport(deviceId: string): Promise<DevicePassportResponse> {
    return deviceAiGet<DevicePassportResponse>(`/devices/${deviceId}/passport`);
  },
  getTrustStatus(deviceId: string): Promise<DeviceTrustStatusResponse> {
    return deviceAiGet<DeviceTrustStatusResponse>(`/devices/${deviceId}/trust`);
  },
  verifyPassport(deviceId: string): Promise<DevicePassportVerificationResponse> {
    return deviceAiGet<DevicePassportVerificationResponse>(`/devices/${deviceId}/passport/verify`);
  },
};
