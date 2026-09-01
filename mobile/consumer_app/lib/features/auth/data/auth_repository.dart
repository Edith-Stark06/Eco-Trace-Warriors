import 'package:dio/dio.dart';

import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/storage/secure_storage_service.dart';
import '../../../core/utils/result.dart';
import '../models/auth_models.dart';

/// Talks to `backend/`'s auth module (`POST /auth/register|login|refresh|logout`,
/// `GET /auth/me`). Unlike the Collector app, `register()` is real and used
/// here: `POST /auth/register` always creates a `CONSUMER` account
/// (`backend/src/modules/auth/auth.service.ts`), which is exactly this app's
/// role — see `reports/P6_3_MOBILE_COLLECTOR.md` §2.1 for why that same fact
/// meant the *Collector* app could not offer self-registration.
class AuthRepository {
  AuthRepository({required ApiClient apiClient, required SecureStorageService secureStorage})
      : _apiClient = apiClient,
        _secureStorage = secureStorage;

  final ApiClient _apiClient;
  final SecureStorageService _secureStorage;

  Future<Result<ConsumerProfile>> register({
    required String email,
    required String password,
    required String confirmPassword,
    required String fullName,
    String? phone,
    String? region,
  }) async {
    try {
      final response = await _apiClient.post(
        '/auth/register',
        data: {
          'email': email,
          'password': password,
          'confirmPassword': confirmPassword,
          'fullName': fullName,
          if (phone != null && phone.isNotEmpty) 'phone': phone,
          if (region != null && region.isNotEmpty) 'region': region,
        },
      );
      return await _persistAndReturn(response.data as Map<String, dynamic>);
    } on DioException catch (e) {
      return Result.failure(mapDioExceptionToFailure(e));
    }
  }

  Future<Result<ConsumerProfile>> login({
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

      if (!result.profile.isConsumer) {
        // The backend authenticates any role; this app is consumer-only.
        // Reject client-side rather than silently showing a collector/admin
        // account inside consumer-shaped screens (rewards, submissions-as-
        // owner) that don't match what that role actually does — the same
        // pattern already used by the Collector app's login (P8.4; see
        // mobile/collector_app/lib/features/auth/data/auth_repository.dart).
        return Result.failure(
          AppFailure.validation(
            'This account is registered as ${result.profile.role}, not CONSUMER. '
            'Use the EcoTrace Consumer app only with a consumer account.',
          ),
        );
      }

      await _secureStorage.saveAuthToken(result.tokens.accessToken);
      await _secureStorage.saveRefreshToken(result.tokens.refreshToken);
      await _secureStorage.saveUserId(result.profile.id);
      return Result.success(result.profile);
    } on DioException catch (e) {
      return Result.failure(mapDioExceptionToFailure(e));
    }
  }

  Future<Result<ConsumerProfile>> _persistAndReturn(Map<String, dynamic> body) async {
    final result = AuthResult.fromJson(body['data'] as Map<String, dynamic>);
    await _secureStorage.saveAuthToken(result.tokens.accessToken);
    await _secureStorage.saveRefreshToken(result.tokens.refreshToken);
    await _secureStorage.saveUserId(result.profile.id);
    return Result.success(result.profile);
  }

  Future<Result<ConsumerProfile>> fetchProfile() async {
    try {
      final response = await _apiClient.get('/auth/me');
      final profile = ConsumerProfile.fromJson(
        (response.data as Map<String, dynamic>)['data'] as Map<String, dynamic>,
      );
      return Result.success(profile);
    } on DioException catch (e) {
      return Result.failure(mapDioExceptionToFailure(e));
    }
  }

  Future<void> logout() async {
    final refreshToken = await _secureStorage.readRefreshToken();
    if (refreshToken != null) {
      try {
        await _apiClient.post('/auth/logout', data: {'refreshToken': refreshToken});
      } on DioException {
        // Logout is idempotent server-side; local credential clearing below
        // always happens regardless of network state.
      }
    }
    await _secureStorage.clearAll();
  }

  Future<bool> hasStoredSession() => _secureStorage.hasValidSession();
}
