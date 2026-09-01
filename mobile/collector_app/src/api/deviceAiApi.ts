import { env } from '../config/env';
import { ApiError } from './ApiError';
import type {
  DeviceRegistrationResponse,
  DeviceStateUpdateResponse,
  DevicePassportResponse,
  DeviceTrustStatusResponse,
} from '../types/device';

/**
 * device_ai has no application auth of its own by default (P8.7,
 * SERVICE_API_KEY is opt-in) — see EXPO_PUBLIC_DEVICE_AI_SERVICE_API_KEY.
 * Uses multipart/form-data directly (fetch's FormData) for the image
 * upload endpoints rather than the JSON apiClient.
 */
const SERVICE_API_KEY = process.env.EXPO_PUBLIC_DEVICE_AI_SERVICE_API_KEY;

async function deviceAiRequest<T>(
  path: string,
  init: { method?: string; body?: FormData | object } = {},
): Promise<T> {
  const headers: Record<string, string> = {};
  if (SERVICE_API_KEY) {
    headers['X-Service-Api-Key'] = SERVICE_API_KEY;
  }
  const isFormData = init.body instanceof FormData;
  if (!isFormData && init.body !== undefined) {
    headers['Content-Type'] = 'application/json';
  }

  let response: Response;
  try {
    response = await fetch(`${env.deviceAiBaseUrl}${path}`, {
      method: init.method ?? 'GET',
      headers,
      body: isFormData ? (init.body as FormData) : init.body ? JSON.stringify(init.body) : undefined,
    });
  } catch {
    throw new ApiError('Unable to reach the device intelligence service.', {
      code: 'NETWORK_ERROR',
      status: null,
    });
  }

  const json = await response.json().catch(() => null);
  if (!response.ok || !json) {
    throw new ApiError(json?.detail ?? `Device AI request failed (${response.status}).`, {
      code: 'DEVICE_AI_ERROR',
      status: response.status,
    });
  }
  return json as T;
}

/** A captured photo, ready to attach to a multipart request. */
export interface CapturedImage {
  uri: string;
  name: string;
  type: string;
}

function toFormData(images: CapturedImage[], captureId?: string): FormData {
  const form = new FormData();
  for (const image of images) {
    // React Native's fetch FormData accepts this { uri, name, type } shape directly.
    form.append('images', { uri: image.uri, name: image.name, type: image.type } as unknown as Blob);
  }
  if (captureId) {
    form.append('capture_id', captureId);
  }
  return form;
}

export const deviceAiApi = {
  registerDevices(images: CapturedImage[], captureId?: string): Promise<DeviceRegistrationResponse> {
    return deviceAiRequest<DeviceRegistrationResponse>('/devices/register', {
      method: 'POST',
      body: toFormData(images, captureId),
    });
  },
  confirm(deviceId: string): Promise<DeviceStateUpdateResponse> {
    return deviceAiRequest<DeviceStateUpdateResponse>(`/devices/${deviceId}/confirm`, { method: 'POST' });
  },
  finalize(deviceId: string): Promise<DeviceStateUpdateResponse> {
    return deviceAiRequest<DeviceStateUpdateResponse>(`/devices/${deviceId}/finalize`, { method: 'POST' });
  },
  getPassport(deviceId: string): Promise<DevicePassportResponse> {
    return deviceAiRequest<DevicePassportResponse>(`/devices/${deviceId}/passport`);
  },
  getTrustStatus(deviceId: string): Promise<DeviceTrustStatusResponse> {
    return deviceAiRequest<DeviceTrustStatusResponse>(`/devices/${deviceId}/trust`);
  },
};
