/// Runtime configuration for the EcoTrace Collector app.
///
/// Nothing here is hard-coded for a specific deployment: the API base URL is
/// read from a compile-time define (`--dart-define=API_BASE_URL=...`) so the
/// same build artifact can point at a local dev backend, a staging server,
/// or production without a source change. See `docs/engineering/` for the
/// EcoTrace backend contract this app talks to.
class AppConfig {
  const AppConfig._();

  /// Base URL of the EcoTrace backend (`backend/` — Express/Prisma; see
  /// `backend/src/app.ts`). Not the Python `intelligence/device_ai` AI
  /// microservice (port 8100) — the collector app talks to the main backend's
  /// auth/submission/collector-workflow API.
  ///
  /// Defaults to the local dev server as seen from the Android emulator
  /// (`10.0.2.2` aliases the host machine's `localhost`). Override at build
  /// time: `flutter build apk --dart-define=API_BASE_URL=https://api.ecotrace.example`
  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:3000',
  );

  /// API path prefix every route is mounted under (`backend/.env.example`:
  /// `API_PREFIX=/api/v1`).
  static const String apiPrefix = String.fromEnvironment(
    'API_PREFIX',
    defaultValue: '/api/v1',
  );

  /// Request timeout for ordinary API calls.
  static const Duration requestTimeout = Duration(seconds: 30);

  /// Longer timeout for multipart image uploads.
  static const Duration uploadTimeout = Duration(seconds: 60);

  /// Interval the sync manager uses to retry queued submissions once
  /// connectivity is restored.
  static const Duration syncRetryInterval = Duration(seconds: 30);

  /// Maximum automatic retry attempts per queued submission before it is
  /// marked `failed` and surfaced to the collector for manual retry.
  static const int maxSyncRetries = 5;

  /// Name of the local SQLite database file (offline cache + sync queue).
  static const String databaseName = 'ecotrace_collector.db';

  /// Secure-storage key for the bearer auth token. Never logged, never
  /// stored outside `flutter_secure_storage` (platform keychain/keystore).
  static const String authTokenKey = 'ecotrace_auth_token';

  /// Secure-storage key for the refresh token.
  static const String refreshTokenKey = 'ecotrace_refresh_token';

  /// Secure-storage key for the cached collector profile id.
  static const String collectorIdKey = 'ecotrace_collector_id';
}
