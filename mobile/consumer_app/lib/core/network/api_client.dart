import 'package:dio/dio.dart';
import 'package:uuid/uuid.dart';

import '../config/app_config.dart';
import '../storage/secure_storage_service.dart';

/// Thin wrapper around [Dio] configured for the EcoTrace backend.
///
/// Responsibilities kept deliberately narrow: base URL/timeouts, attaching
/// the bearer token, attaching an `X-Request-ID` correlation header to every
/// request (mirrors the backend's own request-context middleware), and
/// translating transport-level failures into the app's `AppFailure` model
/// one layer up (in each repository, not here — this class stays a plain
/// HTTP client, not a business-logic layer).
class ApiClient {
  ApiClient({required SecureStorageService secureStorage, Dio? dio})
      : _secureStorage = secureStorage,
        _dio = dio ??
            Dio(
              BaseOptions(
                baseUrl: '${AppConfig.apiBaseUrl}${AppConfig.apiPrefix}',
                connectTimeout: AppConfig.requestTimeout,
                receiveTimeout: AppConfig.requestTimeout,
                sendTimeout: AppConfig.uploadTimeout,
              ),
            ) {
    _dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) async {
          options.headers['X-Request-ID'] = const Uuid().v4();
          final token = await _secureStorage.readAuthToken();
          if (token != null && token.isNotEmpty) {
            options.headers['Authorization'] = 'Bearer $token';
          }
          handler.next(options);
        },
      ),
    );
  }

  final Dio _dio;
  final SecureStorageService _secureStorage;

  Dio get raw => _dio;

  Future<Response<dynamic>> get(
    String path, {
    Map<String, dynamic>? queryParameters,
  }) {
    return _dio.get(path, queryParameters: queryParameters);
  }

  Future<Response<dynamic>> post(
    String path, {
    dynamic data,
    Options? options,
  }) {
    return _dio.post(path, data: data, options: options);
  }

  Future<Response<dynamic>> patch(
    String path, {
    dynamic data,
    Options? options,
  }) {
    return _dio.patch(path, data: data, options: options);
  }

  Future<Response<dynamic>> delete(
    String path, {
    dynamic data,
    Options? options,
  }) {
    return _dio.delete(path, data: data, options: options);
  }
}
