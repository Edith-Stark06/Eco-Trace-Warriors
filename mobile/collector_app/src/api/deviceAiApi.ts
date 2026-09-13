import { Platform } from 'react-native';
import { File as ExpoFile } from 'expo-file-system';
import { env } from '../config/env';
import { ApiError } from './ApiError';
import type {
  DeviceRegistrationResponse,
  DeviceStateUpdateResponse,
  DevicePassportResponse,
  DeviceTrustStatusResponse,
  DeviceEnrichmentResponse,
  TrustAnchorResponse,
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
 * Form part representation providing binary bytes for Expo's FormData converter.
 * Expo 57's convertFormDataAsync() natively serializes entries that expose a `bytes()` method.
 */
export interface FormDataBytePart {
  name: string;
  type: string;
  bytes: () => Promise<Uint8Array>;
}

export type FormPart = Blob | FormDataBytePart;

/**
 * Converts a captured image into a multipart FormData part compatible with
 * the platform runtime:
 *
 * Native (Android/iOS): In Expo 57 with Winter fetch runtime, native FormData
 * serialization (convertFormDataAsync) expects strings, Blobs, or objects with
 * a `bytes(): Promise<Uint8Array>` method. We use `expo-file-system`'s `File`
 * to access local `file://` URIs directly from storage without failing through
 * OkHttp's file URL interceptor.
 *
 * Web: Browser camera capture produces canvas-based `data:` or `blob:` URIs,
 * which `fetch(image.uri)` reads directly into a standard W3C `Blob`.
 */
async function toFormPart(image: CapturedImage): Promise<FormPart> {
  if (Platform.OS === 'web') {
    const res = await fetch(image.uri);
    if (!res.ok) {
      throw new Error(`Unable to read captured image (${res.status}).`);
    }
    const blob = await res.blob();
    if (blob.size === 0) {
      throw new Error('Captured image is empty.');
    }
    return blob;
  }

  const file = new ExpoFile(image.uri);
  if (!file.exists) {
    throw new Error(`Captured image file not found at ${image.uri}.`);
  }
  if (file.size === 0) {
    throw new Error('Captured image is empty.');
  }

  return {
    name: image.name,
    type: image.type || 'image/jpeg',
    bytes: () => file.bytes(),
  };
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
  /** Runs brand/condition/material/carbon intelligence enrichment on a finalized device. */
  enrich(deviceId: string): Promise<DeviceEnrichmentResponse> {
    return deviceAiRequest<DeviceEnrichmentResponse>(`/devices/${deviceId}/enrich`, { method: 'POST' });
  },
  /** Verifies and anchors the Device Passport in the local Trust Anchor layer. Idempotent. */
  anchorPassport(deviceId: string): Promise<TrustAnchorResponse> {
    return deviceAiRequest<TrustAnchorResponse>(`/devices/${deviceId}/passport/anchor`, {
      method: 'POST',
    });
  },
  getPassport(deviceId: string): Promise<DevicePassportResponse> {
    return deviceAiRequest<DevicePassportResponse>(`/devices/${deviceId}/passport`);
  },
  getTrustStatus(deviceId: string): Promise<DeviceTrustStatusResponse> {
    return deviceAiRequest<DeviceTrustStatusResponse>(`/devices/${deviceId}/trust`);
  },
};
