import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../config/app_config.dart';

/// Secure, platform-backed storage for authentication tokens.
///
/// Uses the Android Keystore / iOS Keychain via `flutter_secure_storage` —
/// tokens are never written to `SharedPreferences`, plain files, or logged.
/// This is the single place the app touches token storage; every other
/// layer goes through this service rather than reading secure storage
/// directly, so the security boundary stays auditable in one file.
class SecureStorageService {
  SecureStorageService({FlutterSecureStorage? storage})
      : _storage = storage ??
            // AndroidOptions()'s defaults (flutter_secure_storage 11.x) are
            // already AES-GCM + RSA-OAEP key wrapping — no flag needed.
            const FlutterSecureStorage(aOptions: AndroidOptions());

  final FlutterSecureStorage _storage;

  Future<void> saveAuthToken(String token) =>
      _storage.write(key: AppConfig.authTokenKey, value: token);

  Future<String?> readAuthToken() => _storage.read(key: AppConfig.authTokenKey);

  Future<void> saveRefreshToken(String token) =>
      _storage.write(key: AppConfig.refreshTokenKey, value: token);

  Future<String?> readRefreshToken() => _storage.read(key: AppConfig.refreshTokenKey);

  Future<void> saveUserId(String userId) =>
      _storage.write(key: AppConfig.userIdKey, value: userId);

  Future<String?> readUserId() => _storage.read(key: AppConfig.userIdKey);

  /// Clears all stored credentials — called on logout or on an
  /// unrecoverable auth failure (e.g. a 401 the refresh flow can't resolve).
  Future<void> clearAll() async {
    await _storage.delete(key: AppConfig.authTokenKey);
    await _storage.delete(key: AppConfig.refreshTokenKey);
    await _storage.delete(key: AppConfig.userIdKey);
  }

  Future<bool> hasValidSession() async {
    final token = await readAuthToken();
    return token != null && token.isNotEmpty;
  }
}
