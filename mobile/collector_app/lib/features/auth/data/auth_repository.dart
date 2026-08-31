import 'package:dio/dio.dart';

import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/storage/secure_storage_service.dart';
import '../../../core/utils/result.dart';
import '../models/auth_models.dart';

/// Talks to the real `backend/` auth module
/// (`POST /auth/login|refresh|logout`, `GET /auth/me`).
///
/// Deliberately does **not** expose a `register()` call: the backend's
/// `POST /auth/register` unconditionally creates a `CONSUMER` account
/// (`backend/src/modules/auth/auth.service.ts` — `findRoleId(UserRole.CONSUMER)`
/// is hard-coded; there is no role parameter in `registerSchema`). A
/// self-service "create a collector account" flow does not exist on this
/// backend, so the Collector app does not pretend it does — see
/// `reports/P6_3_MOBILE_COLLECTOR.md` for the full rationale. Collector
/// accounts are provisioned out-of-band (seed data / a future admin
/// provisioning flow, out of scope here).
class AuthRepository {
  AuthRepository({required ApiClient apiClient, required SecureStorageService secureStorage})
      : _apiClient = apiClient,
        _secureStorage = secureStorage;

  final ApiClient _apiClient;
  final SecureStorageService _secureStorage;

  Future<Result<CollectorProfile>> login({
    required String email,
    required String password,
  }) async {
    try {
      final response = await _apiClient.post(
        '/auth/login',
        data: {'email': email, 'password': password},
      );
      final result = AuthResult.fromJson(
        (response.data as Map<String, dynamic>)['data'] as Map<String, dynamic>,
      );

      if (!result.profile.isCollector) {
        // The backend authenticates any role; this app is collector-only.
        // Reject client-side rather than silently showing a consumer/admin
        // account inside collector-shaped screens.
        return Result.failure(
          AppFailure.validation(
            'This account is registered as ${result.profile.role}, not COLLECTOR. '
            'Use the EcoTrace Collector app only with a collector account.',
          ),
        );
      }

      await _secureStorage.saveAuthToken(result.tokens.accessToken);
      await _secureStorage.saveRefreshToken(result.tokens.refreshToken);
      await _secureStorage.saveCollectorId(result.profile.id);
      return Result.success(result.profile);
    } on DioException catch (e) {
      return Result.failure(mapDioExceptionToFailure(e));
    }
  }

  Future<Result<CollectorProfile>> fetchProfile() async {
    try {
      final response = await _apiClient.get('/auth/me');
      final profile = CollectorProfile.fromJson(
        (response.data as Map<String, dynamic>)['data'] as Map<String, dynamic>,
      );
      return Result.success(profile);
    } on DioException catch (e) {
      return Result.failure(mapDioExceptionToFailure(e));
    }
  }

  /// Attempts to refresh the access token. Returns `false` (without
  /// throwing) when the refresh token itself is invalid/expired — the
  /// caller should then force a re-login rather than treat this as a
  /// transient/retryable failure.
  Future<bool> refreshSession() async {
    final refreshToken = await _secureStorage.readRefreshToken();
    if (refreshToken == null) return false;
    try {
      final response = await _apiClient.post(
        '/auth/refresh',
        data: {'refreshToken': refreshToken},
      );
      final tokens = AuthTokens.fromJson(
        (response.data as Map<String, dynamic>)['data'] as Map<String, dynamic>,
      );
      await _secureStorage.saveAuthToken(tokens.accessToken);
      await _secureStorage.saveRefreshToken(tokens.refreshToken);
      return true;
    } on DioException {
      return false;
    }
  }

  Future<void> logout() async {
    final refreshToken = await _secureStorage.readRefreshToken();
    if (refreshToken != null) {
      try {
        await _apiClient.post('/auth/logout', data: {'refreshToken': refreshToken});
      } on DioException {
        // Logout is best-effort server-side (idempotent per the backend's
        // own contract); local credential clearing below always happens.
      }
    }
    await _secureStorage.clearAll();
  }

  Future<bool> hasStoredSession() => _secureStorage.hasValidSession();
}
