import { Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';
import { secureStorage } from './secureStorage';

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

const secureStoreMock = SecureStore as jest.Mocked<typeof SecureStore>;

const ACCESS_KEY = 'ecotrace_consumer_access_token';
const REFRESH_KEY = 'ecotrace_consumer_refresh_token';

/** In-memory stand-in for the browser's `localStorage`, keyed like the real thing. */
function makeFakeLocalStorage() {
  const store = new Map<string, string>();
  return {
    store,
    getItem: jest.fn((key: string) => store.get(key) ?? null),
    setItem: jest.fn((key: string, value: string) => {
      store.set(key, value);
    }),
    removeItem: jest.fn((key: string) => {
      store.delete(key);
    }),
  };
}

describe('secureStorage — native (expo-secure-store)', () => {
  const originalOS = Platform.OS;

  beforeEach(() => {
    jest.clearAllMocks();
    Platform.OS = 'ios';
  });

  afterAll(() => {
    Platform.OS = originalOS;
  });

  it('set/get: setTokens writes both tokens, getAccessToken/getRefreshToken read them back', async () => {
    secureStoreMock.setItemAsync.mockResolvedValue(undefined);
    await secureStorage.setTokens('native-access', 'native-refresh');
    expect(secureStoreMock.setItemAsync).toHaveBeenCalledWith(ACCESS_KEY, 'native-access');
    expect(secureStoreMock.setItemAsync).toHaveBeenCalledWith(REFRESH_KEY, 'native-refresh');

    secureStoreMock.getItemAsync.mockImplementation((key: string) =>
      Promise.resolve(key === ACCESS_KEY ? 'native-access' : 'native-refresh'),
    );
    await expect(secureStorage.getAccessToken()).resolves.toBe('native-access');
    await expect(secureStorage.getRefreshToken()).resolves.toBe('native-refresh');
  });

  it('delete: clearTokens deletes both keys via expo-secure-store', async () => {
    secureStoreMock.deleteItemAsync.mockResolvedValue(undefined);
    await secureStorage.clearTokens();
    expect(secureStoreMock.deleteItemAsync).toHaveBeenCalledWith(ACCESS_KEY);
    expect(secureStoreMock.deleteItemAsync).toHaveBeenCalledWith(REFRESH_KEY);
  });

  it('missing key: resolves null when expo-secure-store has no entry', async () => {
    secureStoreMock.getItemAsync.mockResolvedValue(null);
    await expect(secureStorage.getAccessToken()).resolves.toBeNull();
  });

  it('never touches localStorage on native', async () => {
    const fakeLocalStorage = makeFakeLocalStorage();
    // @ts-expect-error test-only global shim; no localStorage typing outside web
    globalThis.localStorage = fakeLocalStorage;
    secureStoreMock.setItemAsync.mockResolvedValue(undefined);

    await secureStorage.setTokens('a', 'b');

    expect(fakeLocalStorage.setItem).not.toHaveBeenCalled();
    // @ts-expect-error cleanup of the test-only shim
    delete globalThis.localStorage;
  });
});

describe('secureStorage — web (localStorage fallback, Consumer Web SecureStore defect)', () => {
  const originalOS = Platform.OS;
  let fakeLocalStorage: ReturnType<typeof makeFakeLocalStorage>;

  beforeEach(() => {
    jest.clearAllMocks();
    Platform.OS = 'web';
    fakeLocalStorage = makeFakeLocalStorage();
    // @ts-expect-error test-only global shim; no localStorage typing outside web
    globalThis.localStorage = fakeLocalStorage;
  });

  afterEach(() => {
    // @ts-expect-error cleanup of the test-only shim
    delete globalThis.localStorage;
  });

  afterAll(() => {
    Platform.OS = originalOS;
  });

  it('set/get: setTokens persists through localStorage, getAccessToken/getRefreshToken read them back', async () => {
    await secureStorage.setTokens('web-access', 'web-refresh');
    expect(fakeLocalStorage.store.get(ACCESS_KEY)).toBe('web-access');
    expect(fakeLocalStorage.store.get(REFRESH_KEY)).toBe('web-refresh');
    await expect(secureStorage.getAccessToken()).resolves.toBe('web-access');
    await expect(secureStorage.getRefreshToken()).resolves.toBe('web-refresh');
  });

  it('delete: clearTokens removes both keys from localStorage', async () => {
    await secureStorage.setTokens('a', 'b');
    await secureStorage.clearTokens();
    expect(fakeLocalStorage.store.has(ACCESS_KEY)).toBe(false);
    expect(fakeLocalStorage.store.has(REFRESH_KEY)).toBe(false);
    await expect(secureStorage.getAccessToken()).resolves.toBeNull();
  });

  it('missing key: resolves null when nothing was ever stored', async () => {
    await expect(secureStorage.getAccessToken()).resolves.toBeNull();
  });

  it('never calls expo-secure-store on web (the getValueWithKeyAsync regression)', async () => {
    await secureStorage.setTokens('a', 'b');
    await secureStorage.getAccessToken();
    await secureStorage.clearTokens();

    expect(secureStoreMock.setItemAsync).not.toHaveBeenCalled();
    expect(secureStoreMock.getItemAsync).not.toHaveBeenCalled();
    expect(secureStoreMock.deleteItemAsync).not.toHaveBeenCalled();
  });

  it('degrades to a no-op instead of throwing when localStorage is unavailable', async () => {
    // @ts-expect-error cleanup of the test-only shim
    delete globalThis.localStorage;

    await expect(secureStorage.getAccessToken()).resolves.toBeNull();
    await expect(secureStorage.setTokens('a', 'b')).resolves.toBeUndefined();
    await expect(secureStorage.clearTokens()).resolves.toBeUndefined();
  });
});

describe('secureStorage — logging safety', () => {
  const originalOS = Platform.OS;
  const secret = 'super-secret-token-value-should-never-be-logged';

  afterEach(() => {
    Platform.OS = originalOS;
    // @ts-expect-error cleanup of the test-only shim
    delete globalThis.localStorage;
  });

  it('never logs token values while storing/reading/clearing on native', async () => {
    Platform.OS = 'ios';
    secureStoreMock.setItemAsync.mockResolvedValue(undefined);
    secureStoreMock.getItemAsync.mockResolvedValue(secret);
    secureStoreMock.deleteItemAsync.mockResolvedValue(undefined);

    const logSpy = jest.spyOn(console, 'log').mockImplementation(() => undefined);
    const warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => undefined);
    const errorSpy = jest.spyOn(console, 'error').mockImplementation(() => undefined);

    await secureStorage.setTokens(secret, secret);
    await secureStorage.getAccessToken();
    await secureStorage.clearTokens();

    const logged = [...logSpy.mock.calls, ...warnSpy.mock.calls, ...errorSpy.mock.calls].flat().map(String);
    expect(logged.some((entry) => entry.includes(secret))).toBe(false);

    logSpy.mockRestore();
    warnSpy.mockRestore();
    errorSpy.mockRestore();
  });

  it('never logs token values while storing/reading/clearing on web', async () => {
    Platform.OS = 'web';
    // @ts-expect-error test-only global shim; no localStorage typing outside web
    globalThis.localStorage = makeFakeLocalStorage();

    const logSpy = jest.spyOn(console, 'log').mockImplementation(() => undefined);
    const warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => undefined);
    const errorSpy = jest.spyOn(console, 'error').mockImplementation(() => undefined);

    await secureStorage.setTokens(secret, secret);
    await secureStorage.getAccessToken();
    await secureStorage.clearTokens();

    const logged = [...logSpy.mock.calls, ...warnSpy.mock.calls, ...errorSpy.mock.calls].flat().map(String);
    expect(logged.some((entry) => entry.includes(secret))).toBe(false);

    logSpy.mockRestore();
    warnSpy.mockRestore();
    errorSpy.mockRestore();
  });
});
