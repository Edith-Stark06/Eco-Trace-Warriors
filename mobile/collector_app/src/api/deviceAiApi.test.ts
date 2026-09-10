import { Platform } from 'react-native';
import { deviceAiApi } from './deviceAiApi';
import { ApiError } from './ApiError';

/**
 * CHANGE-009 / Expo 57: deviceAiApi.registerDevices() converts captured image
 * URIs into real Blobs before appending to FormData across all platforms.
 *
 * In Expo 57's Winter fetch runtime, native FormData serialization
 * (convertFormDataAsync) expects strings, Blobs, or objects with bytes().
 * The legacy React Native `{ uri, name, type }` object is unsupported and fails
 * with "Unsupported FormDataPart implementation".
 *
 * Spies on FormData.prototype.append directly rather than reading back via
 * RN's own FormData polyfill, asserting deviceAiApi's exact FormData contract.
 */

const CAPTURED_IMAGE = {
  uri: 'file:///data/user/0/host.exp.exponent/cache/ExperienceData/.../Camera/photo.jpg',
  name: 'capture-1.jpg',
  type: 'image/jpeg',
};

const WEB_CAPTURED_IMAGE = {
  uri: 'blob:http://localhost:8081/mock-blob-uuid',
  name: 'web-capture-1.jpg',
  type: 'image/jpeg',
};

const REGISTER_RESPONSE = {
  success: true,
  capture_id: 'cap-test',
  total_detected: 1,
  devices: [{ device_id: 'dev-1' }],
  inference_mode: 'single_model',
};

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  } as unknown as Response;
}

/** A real Blob instance the mocked image-fetch resolves to, standing in for real captured bytes. */
function fakeImageBlob(content = 'fake-image-bytes', type = 'image/jpeg'): Blob {
  return new Blob([content], { type });
}

function mockImageResponse(blob: Blob, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    blob: () => Promise.resolve(blob),
  } as unknown as Response;
}

describe('deviceAiApi.registerDevices — platform-safe upload (CHANGE-009 / Expo 57)', () => {
  const originalOS = Platform.OS;
  let appendSpy: jest.SpyInstance;

  beforeEach(() => {
    appendSpy = jest.spyOn(FormData.prototype, 'append');
  });

  afterEach(() => {
    Platform.OS = originalOS;
    appendSpy.mockRestore();
  });

  it('native (android): fetches the local image URI and converts it to a Blob before appending to FormData with filename', async () => {
    Platform.OS = 'android';
    const blob = fakeImageBlob();
    const fetchMock = jest.fn((url: RequestInfo | URL) => {
      if (String(url) === CAPTURED_IMAGE.uri) {
        return Promise.resolve(mockImageResponse(blob));
      }
      return Promise.resolve(jsonResponse(200, REGISTER_RESPONSE));
    });
    globalThis.fetch = fetchMock;

    await deviceAiApi.registerDevices([CAPTURED_IMAGE]);

    const imagesCall = appendSpy.mock.calls.find((call) => call[0] === 'images');
    expect(imagesCall).toBeDefined();
    expect(imagesCall?.[1]).toBe(blob);
    expect(imagesCall?.[1]).toBeInstanceOf(Blob);
    expect(imagesCall?.[2]).toBe(CAPTURED_IMAGE.name);

    // Two fetches: first reads native file URI into a Blob, second sends registration request
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0][0]).toBe(CAPTURED_IMAGE.uri);
    expect(fetchMock.mock.calls[1][0]).toContain('/devices/register');
  });

  it('native (ios): fetches the local image URI and converts it to a Blob before appending to FormData with filename', async () => {
    Platform.OS = 'ios';
    const blob = fakeImageBlob();
    const fetchMock = jest.fn((url: RequestInfo | URL) => {
      if (String(url) === CAPTURED_IMAGE.uri) {
        return Promise.resolve(mockImageResponse(blob));
      }
      return Promise.resolve(jsonResponse(200, REGISTER_RESPONSE));
    });
    globalThis.fetch = fetchMock;

    await deviceAiApi.registerDevices([CAPTURED_IMAGE]);

    const imagesCall = appendSpy.mock.calls.find((call) => call[0] === 'images');
    expect(imagesCall).toBeDefined();
    expect(imagesCall?.[1]).toBe(blob);
    expect(imagesCall?.[1]).toBeInstanceOf(Blob);
    expect(imagesCall?.[2]).toBe(CAPTURED_IMAGE.name);
    expect(fetchMock.mock.calls[0][0]).toBe(CAPTURED_IMAGE.uri);
  });

  it('web: converts the captured URI into a real Blob before appending, preserving web compatibility', async () => {
    Platform.OS = 'web';
    const blob = fakeImageBlob();
    const fetchMock = jest.fn((url: RequestInfo | URL) => {
      if (String(url) === WEB_CAPTURED_IMAGE.uri) {
        return Promise.resolve(mockImageResponse(blob));
      }
      return Promise.resolve(jsonResponse(200, REGISTER_RESPONSE));
    });
    globalThis.fetch = fetchMock;

    await deviceAiApi.registerDevices([WEB_CAPTURED_IMAGE]);

    const imagesCall = appendSpy.mock.calls.find((call) => call[0] === 'images');
    expect(imagesCall).toBeDefined();
    expect(imagesCall?.[1]).toBe(blob);
    expect(imagesCall?.[1]).toBeInstanceOf(Blob);
    expect(imagesCall?.[2]).toBe(WEB_CAPTURED_IMAGE.name);

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0][0]).toBe(WEB_CAPTURED_IMAGE.uri);
    expect(fetchMock.mock.calls[1][0]).toContain('/devices/register');
  });

  it('device AI registration request is made after the image Blob is prepared with FormData body', async () => {
    Platform.OS = 'android';
    const blob = fakeImageBlob();
    const callOrder: string[] = [];
    const fetchMock = jest.fn((url: RequestInfo | URL, _init?: RequestInit) => {
      const urlStr = String(url);
      if (urlStr === CAPTURED_IMAGE.uri) {
        callOrder.push('fetch-image');
        return Promise.resolve(mockImageResponse(blob));
      }
      callOrder.push('device-ai-register');
      return Promise.resolve(jsonResponse(200, REGISTER_RESPONSE));
    });
    globalThis.fetch = fetchMock;

    await deviceAiApi.registerDevices([CAPTURED_IMAGE]);

    expect(callOrder).toEqual(['fetch-image', 'device-ai-register']);

    const registerCall = fetchMock.mock.calls.find((call) => String(call[0]).includes('/devices/register'));
    expect(registerCall).toBeDefined();
    expect(registerCall?.[1]?.method).toBe('POST');
    expect(registerCall?.[1]?.body).toBeInstanceOf(FormData);
  });

  it('never manually sets a multipart Content-Type header (the runtime must set its own boundary)', async () => {
    Platform.OS = 'android';
    const fetchMock = jest.fn((url: RequestInfo | URL, _init?: RequestInit) => {
      if (String(url) === CAPTURED_IMAGE.uri) {
        return Promise.resolve(mockImageResponse(fakeImageBlob()));
      }
      return Promise.resolve(jsonResponse(200, REGISTER_RESPONSE));
    });
    globalThis.fetch = fetchMock;

    await deviceAiApi.registerDevices([CAPTURED_IMAGE]);

    const registerCall = fetchMock.mock.calls.find((call) => String(call[0]).includes('/devices/register'));
    const headers = registerCall?.[1]?.headers as Record<string, string> | undefined;
    expect(headers?.['Content-Type']).toBeUndefined();
    expect(headers?.['content-type']).toBeUndefined();
  });

  it('includes capture_id as a plain form field alongside the image part', async () => {
    Platform.OS = 'android';
    globalThis.fetch = jest.fn((url: RequestInfo | URL) => {
      if (String(url) === CAPTURED_IMAGE.uri) {
        return Promise.resolve(mockImageResponse(fakeImageBlob()));
      }
      return Promise.resolve(jsonResponse(200, REGISTER_RESPONSE));
    });

    await deviceAiApi.registerDevices([CAPTURED_IMAGE], 'cap-42');

    const captureIdCall = appendSpy.mock.calls.find((call) => call[0] === 'capture_id');
    expect(captureIdCall?.[1]).toBe('cap-42');
  });

  it('throws an error if reading the captured image fails with a non-ok response', async () => {
    globalThis.fetch = jest.fn((url: RequestInfo | URL) => {
      if (String(url) === CAPTURED_IMAGE.uri) {
        return Promise.resolve(mockImageResponse(fakeImageBlob(), 404));
      }
      return Promise.resolve(jsonResponse(200, REGISTER_RESPONSE));
    });

    await expect(deviceAiApi.registerDevices([CAPTURED_IMAGE])).rejects.toThrow(
      'Unable to read captured image (404).',
    );
  });

  it('throws an error if the captured image blob is empty (0 bytes)', async () => {
    const emptyBlob = fakeImageBlob('');
    globalThis.fetch = jest.fn((url: RequestInfo | URL) => {
      if (String(url) === CAPTURED_IMAGE.uri) {
        return Promise.resolve(mockImageResponse(emptyBlob, 200));
      }
      return Promise.resolve(jsonResponse(200, REGISTER_RESPONSE));
    });

    await expect(deviceAiApi.registerDevices([CAPTURED_IMAGE])).rejects.toThrow(
      'Captured image is empty.',
    );
  });

  it('existing response contract: resolves with the parsed JSON body on success', async () => {
    Platform.OS = 'android';
    globalThis.fetch = jest.fn((url: RequestInfo | URL) => {
      if (String(url) === CAPTURED_IMAGE.uri) {
        return Promise.resolve(mockImageResponse(fakeImageBlob()));
      }
      return Promise.resolve(jsonResponse(200, REGISTER_RESPONSE));
    });

    const result = await deviceAiApi.registerDevices([CAPTURED_IMAGE]);
    expect(result).toEqual(REGISTER_RESPONSE);
  });

  it('existing response contract: throws ApiError with the response status on failure', async () => {
    Platform.OS = 'android';
    globalThis.fetch = jest.fn((url: RequestInfo | URL) => {
      if (String(url) === CAPTURED_IMAGE.uri) {
        return Promise.resolve(mockImageResponse(fakeImageBlob()));
      }
      return Promise.resolve(
        jsonResponse(422, {
          detail: 'Request payload failed validation.',
        }),
      );
    });

    await expect(deviceAiApi.registerDevices([CAPTURED_IMAGE])).rejects.toThrow(ApiError);
    await expect(deviceAiApi.registerDevices([CAPTURED_IMAGE])).rejects.toMatchObject({
      code: 'DEVICE_AI_ERROR',
      status: 422,
      message: 'Request payload failed validation.',
    });
  });

  it('existing response contract: throws ApiError with NETWORK_ERROR when device AI is unreachable', async () => {
    globalThis.fetch = jest.fn((url: RequestInfo | URL) => {
      if (String(url) === CAPTURED_IMAGE.uri) {
        return Promise.resolve(mockImageResponse(fakeImageBlob()));
      }
      return Promise.reject(new Error('Network request failed'));
    });

    await expect(deviceAiApi.registerDevices([CAPTURED_IMAGE])).rejects.toMatchObject({
      code: 'NETWORK_ERROR',
      message: 'Unable to reach the device intelligence service.',
    });
  });
});

describe('deviceAiApi lifecycle methods', () => {
  it('confirm: sends POST /devices/:id/confirm', async () => {
    const mockRes = { success: true, current_state: 'CONFIRMED' };
    const fetchMock = jest.fn().mockResolvedValue(jsonResponse(200, mockRes));
    globalThis.fetch = fetchMock;

    const result = await deviceAiApi.confirm('dev-123');
    expect(result).toEqual(mockRes);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/devices/dev-123/confirm'),
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('finalize: sends POST /devices/:id/finalize', async () => {
    const mockRes = { success: true, current_state: 'REGISTERED' };
    const fetchMock = jest.fn().mockResolvedValue(jsonResponse(200, mockRes));
    globalThis.fetch = fetchMock;

    const result = await deviceAiApi.finalize('dev-123');
    expect(result).toEqual(mockRes);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/devices/dev-123/finalize'),
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('getPassport: sends GET /devices/:id/passport', async () => {
    const mockRes = { device_id: 'dev-123', passport: {} };
    const fetchMock = jest.fn().mockResolvedValue(jsonResponse(200, mockRes));
    globalThis.fetch = fetchMock;

    const result = await deviceAiApi.getPassport('dev-123');
    expect(result).toEqual(mockRes);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/devices/dev-123/passport'),
      expect.objectContaining({ method: 'GET' }),
    );
  });

  it('getTrustStatus: sends GET /devices/:id/trust', async () => {
    const mockRes = { device_id: 'dev-123', trust_score: 0.95 };
    const fetchMock = jest.fn().mockResolvedValue(jsonResponse(200, mockRes));
    globalThis.fetch = fetchMock;

    const result = await deviceAiApi.getTrustStatus('dev-123');
    expect(result).toEqual(mockRes);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/devices/dev-123/trust'),
      expect.objectContaining({ method: 'GET' }),
    );
  });
});
