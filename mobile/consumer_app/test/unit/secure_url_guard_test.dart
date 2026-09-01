import 'package:ecotrace_consumer/core/config/secure_url_guard.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('assertSecureApiUrl', () {
    test('allows a plain-HTTP URL in debug/profile mode (local dev, P8.7)', () {
      expect(
        () => assertSecureApiUrl(url: 'http://10.0.2.2:3000', isReleaseMode: false),
        returnsNormally,
      );
    });

    test('allows an HTTPS URL in release mode', () {
      expect(
        () => assertSecureApiUrl(url: 'https://api.ecotrace.example', isReleaseMode: true),
        returnsNormally,
      );
    });

    test('throws in release mode against the plain-HTTP local-dev default (P8.7)', () {
      expect(
        () => assertSecureApiUrl(url: 'http://10.0.2.2:3000', isReleaseMode: true),
        throwsA(isA<InsecureApiUrlError>()),
      );
    });

    test('the thrown error message names the offending URL', () {
      try {
        assertSecureApiUrl(url: 'http://insecure.example', isReleaseMode: true);
        fail('expected InsecureApiUrlError');
      } on InsecureApiUrlError catch (e) {
        expect(e.toString(), contains('http://insecure.example'));
      }
    });
  });
}
