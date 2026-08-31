/// Runtime configuration for the EcoTrace Consumer app.
///
/// Talks to the same `backend/` (Express/Prisma) service as the Collector
/// app — see `mobile/collector_app/lib/core/config/app_config.dart` and
/// `reports/P6_3_MOBILE_COLLECTOR.md` for how that contract was verified
/// against actual backend source, not assumed.
class AppConfig {
  const AppConfig._();

  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:3000',
  );

  static const String apiPrefix = String.fromEnvironment(
    'API_PREFIX',
    defaultValue: '/api/v1',
  );

  static const Duration requestTimeout = Duration(seconds: 30);
  static const Duration uploadTimeout = Duration(seconds: 60);

  static const String authTokenKey = 'ecotrace_consumer_auth_token';
  static const String refreshTokenKey = 'ecotrace_consumer_refresh_token';
  static const String userIdKey = 'ecotrace_consumer_user_id';
}
