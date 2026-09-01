/// Refuses to run a release build against a non-HTTPS API base URL.
///
/// [AppConfig.apiBaseUrl]'s default (`http://10.0.2.2:3000`) only resolves
/// inside an Android emulator talking to a local dev backend — it is never
/// meant to reach a real pilot/production deployment. A release build that
/// forgets `--dart-define=API_BASE_URL=https://...` should fail loudly at
/// startup, not ship silently. Mirrors the same "refuse insecure defaults
/// in production" pattern already enforced server-side by
/// `backend/src/shared/config/env.schema.ts`.
///
/// Takes both values as parameters (rather than reading `AppConfig`/
/// `kReleaseMode` directly) so the decision logic is unit-testable without
/// needing an actual release build.
class InsecureApiUrlError extends Error {
  InsecureApiUrlError(this.url);

  final String url;

  @override
  String toString() =>
      'Refusing to start a release build with a non-HTTPS API base URL '
      '($url). Build with --dart-define=API_BASE_URL=https://... for '
      'anything beyond local emulator development.';
}

void assertSecureApiUrl({required String url, required bool isReleaseMode}) {
  if (isReleaseMode && !url.startsWith('https://')) {
    throw InsecureApiUrlError(url);
  }
}
