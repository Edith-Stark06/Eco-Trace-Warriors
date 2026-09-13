import { Platform } from 'react-native';
import { deviceAiApi } from './deviceAiApi';
import { ApiError } from './ApiError';

/**
 * CHANGE-009 / Expo 57: deviceAiApi.registerDevices() uses expo-file-system's
 * File API to stream native camera file:// URIs as byte parts supported by
 * Expo's convertFormDataAsync(), and uses fetch() -> Blob on web.
 */

const mockFiles = new Map<string, { exists: boolean; size: number; bytes: () => Promise<Uint8Array> }>();

jest.mock('expo-file-system', () => {
  return {
    File: jest.fn().mockImplementation((uri: string) => {
      if (mockFiles.has(uri)) {
        return mockFiles.get(uri);
      }
      return {
        uri,
        exists: true,
        size: 2048,
        bytes: jest.fn().mockResolvedValue(new Uint8Array([0xff, 0xd8, 0xff, 0xe0])),
      };
    }),
  };
});

const CAPTURED_IMAGE = {
  uri: 'file:///data/user/0/host.exp.exponent/cache/ExperienceData/%2540anonymous%252Fcollector_app-test/Camera/photo.jpg',
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

describe('deviceAiApi.registerDevices — Expo 57 filesystem & web uploads', () => {
  const originalOS = Platform.OS;
  let appendSpy: jest.SpyInstance;

  beforeEach(() => {
    mockFiles.clear();
    appendSpy = jest.spyOn(FormData.prototype, 'append');
  });

  afterEach(() => {
    Platform.OS = originalOS;
    appendSpy.mockRestore();
  });

  it('native (android): reads camera file via expo-file-system and appends byte part with filename', async () => {
    Platform.OS = 'android';
    const fetchMock = jest.fn((_url: RequestInfo | URL, _init?: RequestInit) => {
      return Promise.resolve(jsonResponse(200, REGISTER_RESPONSE));
    });
    globalThis.fetch = fetchMock;

    await deviceAiApi.registerDevices([CAPTURED_IMAGE]);

    const imagesCall = appendSpy.mock.calls.find((call) => call[0] === 'images');
    expect(imagesCall).toBeDefined();
    const part = imagesCall?.[1];
    expect(part).toBeDefined();
    expect(typeof part.bytes).toBe('function');
    expect(part.name).toBe(CAPTURED_IMAGE.name);
    expect(part.type).toBe('image/jpeg');

    const bytes = await part.bytes();
    expect(bytes).toBeInstanceOf(Uint8Array);
    expect(bytes.length).toBeGreaterThan(0);

    // Filename and type are preserved on the part object for Expo's FormData converter
    expect(part.name).toBe(CAPTURED_IMAGE.name);
    expect(part.type).toBe('image/jpeg');

    // Registration request is sent
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toContain('/devices/register');
  });

  it('native (ios): reads camera file via expo-file-system and appends byte part with filename', async () => {
    Platform.OS = 'ios';
    const fetchMock = jest.fn((_url: RequestInfo | URL, _init?: RequestInit) => {
      return Promise.resolve(jsonResponse(200, REGISTER_RESPONSE));
    });
    globalThis.fetch = fetchMock;

    await deviceAiApi.registerDevices([CAPTURED_IMAGE]);

    const imagesCall = appendSpy.mock.calls.find((call) => call[0] === 'images');
    expect(imagesCall).toBeDefined();
    const part = imagesCall?.[1];
    expect(typeof part.bytes).toBe('function');
    expect(part.name).toBe(CAPTURED_IMAGE.name);
    expect(part.type).toBe('image/jpeg');
  });

  it('native: throws error when captured image file does not exist', async () => {
    Platform.OS = 'android';
    mockFiles.set(CAPTURED_IMAGE.uri, {
      exists: false,
      size: 0,
      bytes: jest.fn(),
    });

    await expect(deviceAiApi.registerDevices([CAPTURED_IMAGE])).rejects.toThrow(
      `Captured image file not found at ${CAPTURED_IMAGE.uri}.`,
    );
  });

  it('native: throws error when captured image file is empty (0 bytes)', async () => {
    Platform.OS = 'android';
    mockFiles.set(CAPTURED_IMAGE.uri, {
      exists: true,
      size: 0,
      bytes: jest.fn().mockResolvedValue(new Uint8Array(0)),
    });

    await expect(deviceAiApi.registerDevices([CAPTURED_IMAGE])).rejects.toThrow(
      'Captured image is empty.',
    );
  });

  it('web: converts captured URI into a real Blob before appending, preserving web compatibility', async () => {
    Platform.OS = 'web';
    const blob = fakeImageBlob();
    const fetchMock = jest.fn((url: RequestInfo | URL, _init?: RequestInit) => {
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

  it('web: throws error if reading captured image fails with a non-ok response', async () => {
    Platform.OS = 'web';
    globalThis.fetch = jest.fn((url: RequestInfo | URL) => {
      if (String(url) === WEB_CAPTURED_IMAGE.uri) {
        return Promise.resolve(mockImageResponse(fakeImageBlob(), 404));
      }
      return Promise.resolve(jsonResponse(200, REGISTER_RESPONSE));
    });

    await expect(deviceAiApi.registerDevices([WEB_CAPTURED_IMAGE])).rejects.toThrow(
      'Unable to read captured image (404).',
    );
  });

  it('web: throws error if captured image blob is empty (0 bytes)', async () => {
    Platform.OS = 'web';
    const emptyBlob = fakeImageBlob('');
    globalThis.fetch = jest.fn((url: RequestInfo | URL) => {
      if (String(url) === WEB_CAPTURED_IMAGE.uri) {
        return Promise.resolve(mockImageResponse(emptyBlob, 200));
      }
      return Promise.resolve(jsonResponse(200, REGISTER_RESPONSE));
    });

    await expect(deviceAiApi.registerDevices([WEB_CAPTURED_IMAGE])).rejects.toThrow(
      'Captured image is empty.',
    );
  });

  it('device AI registration request is dispatched with FormData body', async () => {
    Platform.OS = 'android';
    const fetchMock = jest.fn((_url: RequestInfo | URL, _init?: RequestInit) => {
      return Promise.resolve(jsonResponse(200, REGISTER_RESPONSE));
    });
    globalThis.fetch = fetchMock;

    await deviceAiApi.registerDevices([CAPTURED_IMAGE]);

    const registerCall = fetchMock.mock.calls.find((call) => String(call[0]).includes('/devices/register'));
    expect(registerCall).toBeDefined();
    expect(registerCall?.[1]?.method).toBe('POST');
    expect(registerCall?.[1]?.body).toBeInstanceOf(FormData);
  });

  it('never manually sets a multipart Content-Type header (the runtime must set its own boundary)', async () => {
    Platform.OS = 'android';
    const fetchMock = jest.fn((_url: RequestInfo | URL, _init?: RequestInit) => {
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
    globalThis.fetch = jest.fn().mockResolvedValue(jsonResponse(200, REGISTER_RESPONSE));

    await deviceAiApi.registerDevices([CAPTURED_IMAGE], 'cap-42');

    const captureIdCall = appendSpy.mock.calls.find((call) => call[0] === 'capture_id');
    expect(captureIdCall?.[1]).toBe('cap-42');
  });

  it('existing response contract: resolves with parsed JSON body on success', async () => {
    Platform.OS = 'android';
    globalThis.fetch = jest.fn().mockResolvedValue(jsonResponse(200, REGISTER_RESPONSE));

    const result = await deviceAiApi.registerDevices([CAPTURED_IMAGE]);
    expect(result).toEqual(REGISTER_RESPONSE);
  });

  it('existing response contract: throws ApiError with response status on failure', async () => {
    Platform.OS = 'android';
    globalThis.fetch = jest.fn().mockResolvedValue(
      jsonResponse(422, {
        detail: 'Request payload failed validation.',
      }),
    );

    await expect(deviceAiApi.registerDevices([CAPTURED_IMAGE])).rejects.toThrow(ApiError);
    await expect(deviceAiApi.registerDevices([CAPTURED_IMAGE])).rejects.toMatchObject({
      code: 'DEVICE_AI_ERROR',
      status: 422,
      message: 'Request payload failed validation.',
    });
  });

  it('existing response contract: throws ApiError with NETWORK_ERROR when device AI is unreachable', async () => {
    Platform.OS = 'android';
    globalThis.fetch = jest.fn().mockRejectedValue(new Error('Network request failed'));

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

  it('enrich: sends POST /devices/:id/enrich', async () => {
    const mockRes = { success: true, device: { device_id: 'dev-123' }, intelligence: {} };
    const fetchMock = jest.fn().mockResolvedValue(jsonResponse(200, mockRes));
    globalThis.fetch = fetchMock;

    const result = await deviceAiApi.enrich('dev-123');
    expect(result).toEqual(mockRes);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/devices/dev-123/enrich'),
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('anchorPassport: sends POST /devices/:id/passport/anchor', async () => {
    const mockRes = { success: true, anchor: { anchor_id: 'anc-1' }, is_new: true };
    const fetchMock = jest.fn().mockResolvedValue(jsonResponse(201, mockRes));
    globalThis.fetch = fetchMock;

    const result = await deviceAiApi.anchorPassport('dev-123');
    expect(result).toEqual(mockRes);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/devices/dev-123/passport/anchor'),
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
