import 'dart:developer' as developer;

import 'package:flutter/foundation.dart';

/// Structured application logging (P7.3).
///
/// Every entry carries a level, a `name` identifying the emitting
/// component, and optional structured `context`/`error`/`stackTrace` —
/// routed through `dart:developer`'s `log()` so entries are filterable and
/// inspectable in DevTools/`flutter logs`, not just raw stdout text.
///
/// Gated by [kDebugMode]: release builds emit nothing, so this is never a
/// production log-shipping mechanism — no backend exists to receive mobile
/// logs (see `mobile/collector_app/pubspec.yaml`: no log-shipping package
/// is a dependency). This is a local diagnostics aid only.
abstract final class AppLogger {
  static void debug(String name, String message, {Map<String, Object?>? context}) {
    _emit(level: 500, name: name, message: message, context: context);
  }

  static void info(String name, String message, {Map<String, Object?>? context}) {
    _emit(level: 800, name: name, message: message, context: context);
  }

  static void warn(String name, String message, {Map<String, Object?>? context}) {
    _emit(level: 900, name: name, message: message, context: context);
  }

  static void error(
    String name,
    String message, {
    Object? error,
    StackTrace? stackTrace,
    Map<String, Object?>? context,
  }) {
    _emit(
      level: 1000,
      name: name,
      message: message,
      context: context,
      error: error,
      stackTrace: stackTrace,
    );
  }

  static void _emit({
    required int level,
    required String name,
    required String message,
    Map<String, Object?>? context,
    Object? error,
    StackTrace? stackTrace,
  }) {
    if (!kDebugMode) return;

    final fullMessage = context == null || context.isEmpty ? message : '$message $context';
    developer.log(
      fullMessage,
      time: DateTime.now(),
      level: level,
      name: 'ecotrace.collector.$name',
      error: error,
      stackTrace: stackTrace,
    );
  }
}
