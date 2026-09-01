import 'package:flutter/foundation.dart' show kReleaseMode;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app.dart';
import 'core/config/app_config.dart';
import 'core/config/secure_url_guard.dart';

void main() {
  assertSecureApiUrl(url: AppConfig.apiBaseUrl, isReleaseMode: kReleaseMode);
  runApp(const ProviderScope(child: EcoTraceCollectorApp()));
}
