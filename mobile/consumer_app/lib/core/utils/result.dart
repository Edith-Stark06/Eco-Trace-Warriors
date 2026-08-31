/// A minimal `Result<T>` type for explicit success/failure handling.
///
/// Repositories and services return `Result<T>` instead of throwing for
/// expected failure modes (network errors, validation errors, auth
/// failures), so UI code handles them deliberately instead of relying on
/// try/catch scattered through widgets.
sealed class Result<T> {
  const Result();

  /// Construct a successful result.
  const factory Result.success(T value) = Success<T>;

  /// Construct a failed result.
  const factory Result.failure(AppFailure failure) = Failure<T>;

  bool get isSuccess => this is Success<T>;
  bool get isFailure => this is Failure<T>;

  /// The success value, or `null` if this is a failure.
  T? get valueOrNull => switch (this) {
        Success<T>(value: final v) => v,
        Failure<T>() => null,
      };

  /// The failure, or `null` if this is a success.
  AppFailure? get failureOrNull => switch (this) {
        Success<T>() => null,
        Failure<T>(failure: final f) => f,
      };

  /// Pattern-match both branches.
  R when<R>({
    required R Function(T value) success,
    required R Function(AppFailure failure) failure,
  }) {
    return switch (this) {
      Success<T>(value: final v) => success(v),
      Failure<T>(failure: final f) => failure(f),
    };
  }
}

final class Success<T> extends Result<T> {
  const Success(this.value);
  final T value;
}

final class Failure<T> extends Result<T> {
  const Failure(this.failure);
  final AppFailure failure;
}

/// Classified application-level failure.
///
/// Mirrors the backend's error envelope (`code`, `message`) where the
/// failure originated from an API call, so a network/API error can be
/// displayed and retried consistently across every screen.
class AppFailure {
  const AppFailure({
    required this.message,
    this.code,
    this.statusCode,
    this.isRetryable = true,
  });

  /// Human-readable message safe to show the collector.
  final String message;

  /// Machine-readable error code from the backend envelope, if any
  /// (e.g. `DEVICE_NOT_FOUND`, `FABRIC_UNAVAILABLE`).
  final String? code;

  /// HTTP status code, if this failure originated from an API call.
  final int? statusCode;

  /// Whether the sync manager should retry this operation automatically.
  /// `false` for validation/auth errors that will never succeed by retrying.
  final bool isRetryable;

  factory AppFailure.network(String message) => AppFailure(
        message: message,
        code: 'NETWORK_ERROR',
        isRetryable: true,
      );

  factory AppFailure.unauthorized() => const AppFailure(
        message: 'Session expired. Please log in again.',
        code: 'UNAUTHORIZED',
        statusCode: 401,
        isRetryable: false,
      );

  factory AppFailure.validation(String message) => AppFailure(
        message: message,
        code: 'VALIDATION_ERROR',
        isRetryable: false,
      );

  factory AppFailure.unknown(String message) => AppFailure(
        message: message,
        code: 'UNKNOWN_ERROR',
        isRetryable: true,
      );

  @override
  String toString() => 'AppFailure(code: $code, message: $message)';
}
