import { Platform } from 'react-native';
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

/**
 * Converts a captured image into the value FormData.append() needs on this
 * platform.
 *
 * Native (iOS/Android): React Native's fetch FormData polyfill accepts the
 * `{ uri, name, type }` shape directly and streams from the native file URI
 * — this is the RN-specific upload convention, not a real Blob/File.
 *
 * Web: the browser's real FormData.append() only accepts a Blob, File, or
 * string. A plain `{ uri, name, type }` object is silently coerced to the
 * string "[object Object]" instead of being rejected — no error, just a
 * multipart text field with no image bytes in it (CHANGE-009). CaptureScreen
 * hands web a data:/blob: URI (from expo-camera's canvas-based web capture),
 * which `fetch()` can read directly and turn into a real Blob.
 */
async function toFormPart(image: CapturedImage): Promise<Blob | { uri: string; name: string; type: string }> {
  if (Platform.OS !== 'web') {
    return { uri: image.uri, name: image.name, type: image.type };
  }
  const res = await fetch(image.uri);
  return res.blob();
}

async function toFormData(images: CapturedImage[], captureId?: string): Promise<FormData> {
  const form = new FormData();
  for (const image of images) {
    const part = await toFormPart(image);
    if (part instanceof Blob) {
      form.append('images', part, image.name);
    } else {
      form.append('images', part as unknown as Blob);
    }
  }
  if (captureId) {
    form.append('capture_id', captureId);
  }
  return form;
}

export const deviceAiApi = {
  async registerDevices(images: CapturedImage[], captureId?: string): Promise<DeviceRegistrationResponse> {
    const body = await toFormData(images, captureId);
    return deviceAiRequest<DeviceRegistrationResponse>('/devices/register', { method: 'POST', body });
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
