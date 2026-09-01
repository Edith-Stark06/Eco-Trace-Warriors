import 'package:ecotrace_collector/core/diagnostics/app_logger.dart';
import 'package:flutter_test/flutter_test.dart';

/// `AppLogger` routes through `dart:developer`'s `log()`, which has no
/// observable return value or interceptable sink from a plain `flutter test`
/// — these are smoke tests proving every call shape is exception-free
/// (argument handling, string interpolation, null-context paths), not
/// assertions on emitted log content.
void main() {
  group('AppLogger', () {
    test('debug/info/warn do not throw with no context', () {
      expect(() => AppLogger.debug('test', 'a debug message'), returnsNormally);
      expect(() => AppLogger.info('test', 'an info message'), returnsNormally);
      expect(() => AppLogger.warn('test', 'a warn message'), returnsNormally);
    });

    test('all levels do not throw with a structured context map', () {
      final context = {'submissionId': 'sub-1', 'action': 'accept', 'retryCount': 2};
      expect(() => AppLogger.debug('sync', 'msg', context: context), returnsNormally);
      expect(() => AppLogger.info('sync', 'msg', context: context), returnsNormally);
      expect(() => AppLogger.warn('sync', 'msg', context: context), returnsNormally);
    });

    test('error() does not throw with an attached error and stack trace', () {
      expect(
        () => AppLogger.error(
          'network',
          'request failed',
          error: Exception('boom'),
          stackTrace: StackTrace.current,
          context: {'statusCode': 500},
        ),
        returnsNormally,
      );
    });

    test('error() does not throw with no error/stackTrace/context supplied', () {
      expect(() => AppLogger.error('network', 'request failed'), returnsNormally);
    });
  });
}
