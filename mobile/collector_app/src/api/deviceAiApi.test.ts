import { Platform } from 'react-native';
import { deviceAiApi } from './deviceAiApi';
import { ApiError } from './ApiError';

/**
 * CHANGE-009: deviceAiApi.registerDevices() must send the RN upload shape
 * on native and a real Blob on web — a plain `{ uri, name, type }` object
 * silently coerces to the string "[object Object]" in a real browser's
 * FormData, producing a text field with no image bytes at all (no error,
 * no throw — just a broken multipart body device_ai then rejects).
 *
 * Spies on FormData.prototype.append directly rather than reading back via
 * RN's own FormData polyfill (the `FormData` global available under
 * jest-expo): that polyfill isn't a substitute for a real browser's
 * FormData, so asserting through its internals would test the polyfill, not
 * deviceAiApi.ts's actual contract with whichever FormData is present.
 */

const CAPTURED_IMAGE = { uri: 'blob:mock-capture-uri', name: 'capture-1.jpg', type: 'image/jpeg' };

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
function fakeImageBlob(): Blob {
  return new Blob(['fake-image-bytes'], { type: 'image/jpeg' });
}

describe('deviceAiApi.registerDevices — platform-safe upload (CHANGE-009)', () => {
  const originalOS = Platform.OS;
  let appendSpy: jest.SpyInstance;

  beforeEach(() => {
    appendSpy = jest.spyOn(FormData.prototype, 'append');
  });

  afterEach(() => {
    Platform.OS = originalOS;
    appendSpy.mockRestore();
  });

  it('native: appends the { uri, name, type } RN upload shape directly, with no intermediate fetch of the image URI', async () => {
    Platform.OS = 'ios';
    const fetchMock = jest.fn().mockResolvedValue(jsonResponse(200, REGISTER_RESPONSE));
    globalThis.fetch = fetchMock;

    await deviceAiApi.registerDevices([CAPTURED_IMAGE]);

    const imagesCall = appendSpy.mock.calls.find((call) => call[0] === 'images');
    expect(imagesCall).toBeDefined();
    expect(imagesCall?.[1]).toEqual({
      uri: CAPTURED_IMAGE.uri,
      name: CAPTURED_IMAGE.name,
      type: CAPTURED_IMAGE.type,
    });
    expect(imagesCall?.[1]).not.toBeInstanceOf(Blob);

    // Exactly one fetch: the device-ai request itself. The image URI is
    // never independently fetched on native — RN's FormData reads it later.
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toContain('/devices/register');
  });

  it('web: converts the captured URI into a real Blob before appending, never the raw RN-shaped object', async () => {
    Platform.OS = 'web';
    const blob = fakeImageBlob();
    const fetchMock = jest.fn((url: RequestInfo | URL) => {
      if (url === CAPTURED_IMAGE.uri) {
        return Promise.resolve({ blob: () => Promise.resolve(blob) } as unknown as Response);
      }
      return Promise.resolve(jsonResponse(200, REGISTER_RESPONSE));
    });
    globalThis.fetch = fetchMock;

    await deviceAiApi.registerDevices([CAPTURED_IMAGE]);

    const imagesCall = appendSpy.mock.calls.find((call) => call[0] === 'images');
    expect(imagesCall).toBeDefined();
    expect(imagesCall?.[1]).toBe(blob);
    expect(imagesCall?.[2]).toBe(CAPTURED_IMAGE.name);

    // Two fetches on web: one to read the captured URI into a Blob, one for
    // the actual device-ai request — and the image URI is fetched first.
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0][0]).toBe(CAPTURED_IMAGE.uri);
    expect(fetchMock.mock.calls[1][0]).toContain('/devices/register');
  });

  it('web: never manually sets a multipart Content-Type header (the browser must set its own boundary)', async () => {
    Platform.OS = 'web';
    const fetchMock = jest.fn((url: RequestInfo | URL, _init?: RequestInit) => {
      if (url === CAPTURED_IMAGE.uri) {
        return Promise.resolve({ blob: () => Promise.resolve(fakeImageBlob()) } as unknown as Response);
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
    Platform.OS = 'ios';
    globalThis.fetch = jest.fn().mockResolvedValue(jsonResponse(200, REGISTER_RESPONSE));

    await deviceAiApi.registerDevices([CAPTURED_IMAGE], 'cap-42');

    const captureIdCall = appendSpy.mock.calls.find((call) => call[0] === 'capture_id');
    expect(captureIdCall?.[1]).toBe('cap-42');
  });

  it('existing response contract: resolves with the parsed JSON body on success', async () => {
    Platform.OS = 'ios';
    globalThis.fetch = jest.fn().mockResolvedValue(jsonResponse(200, REGISTER_RESPONSE));

    const result = await deviceAiApi.registerDevices([CAPTURED_IMAGE]);
    expect(result).toEqual(REGISTER_RESPONSE);
  });

  it('existing response contract: throws ApiError with the response status on failure', async () => {
    Platform.OS = 'ios';
    globalThis.fetch = jest.fn().mockResolvedValue(
      jsonResponse(422, {
        success: false,
        error: { code: 'REQUEST_VALIDATION_ERROR', message: 'Request payload failed validation.' },
      }),
    );

    await expect(deviceAiApi.registerDevices([CAPTURED_IMAGE])).rejects.toThrow(ApiError);
  });
});
