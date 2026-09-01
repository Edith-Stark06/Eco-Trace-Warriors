import 'package:dio/dio.dart';

import '../diagnostics/app_logger.dart';
import '../utils/result.dart';

/// Translates a [DioException] into the app's [AppFailure] model.
///
/// Centralized here so every repository handles backend errors identically
/// — including the standard EcoTrace error envelope
/// `{"error": {"code": ..., "message": ..., "details": {...}}, "request_id": ...}`
/// (see `intelligence/device_ai/api/schemas.py` / `api/errors.py`).
AppFailure mapDioExceptionToFailure(DioException exception) {
  AppLogger.warn(
    'network',
    'Request failed: ${exception.requestOptions.method} ${exception.requestOptions.path}',
    context: {
      'type': exception.type.name,
      'statusCode': exception.response?.statusCode,
    },
  );

  switch (exception.type) {
    case DioExceptionType.connectionTimeout:
    case DioExceptionType.sendTimeout:
    case DioExceptionType.receiveTimeout:
      return AppFailure.network('The request timed out. Check your connection and try again.');
    case DioExceptionType.connectionError:
      return AppFailure.network('Could not reach the EcoTrace server. Check your connection.');
    case DioExceptionType.cancel:
      return const AppFailure(
        message: 'Request cancelled.',
        code: 'CANCELLED',
        isRetryable: false,
      );
    case DioExceptionType.badResponse:
      return _mapErrorResponse(exception);
    case DioExceptionType.badCertificate:
      return const AppFailure(
        message: 'Could not verify the server certificate.',
        code: 'TLS_ERROR',
        isRetryable: false,
      );
    case DioExceptionType.unknown:
    default:
      // `default` covers dio releases that add new DioExceptionType values
      // (e.g. transformTimeout) after this file was written — falling back
      // to the generic classification is preferable to a hard compile break.
      return AppFailure.unknown(exception.message ?? 'An unexpected error occurred.');
  }
}

AppFailure _mapErrorResponse(DioException exception) {
  final statusCode = exception.response?.statusCode;
  final data = exception.response?.data;

  String message = 'The server rejected the request.';
  String? code;

  if (data is Map<String, dynamic>) {
    final errorBody = data['error'];
    if (errorBody is Map<String, dynamic>) {
      message = (errorBody['message'] as String?) ?? message;
      code = errorBody['code'] as String?;
    }
  }

  if (statusCode == 401 || statusCode == 403) {
    return AppFailure.unauthorized();
  }
  if (statusCode != null && statusCode >= 400 && statusCode < 500) {
    return AppFailure(
      message: message,
      code: code,
      statusCode: statusCode,
      isRetryable: statusCode == 409 || statusCode == 429,
    );
  }
  return AppFailure(
    message: message,
    code: code,
    statusCode: statusCode,
    isRetryable: true,
  );
}
