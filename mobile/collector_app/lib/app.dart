import 'package:flutter/material.dart';

import 'core/theme/app_theme.dart';
import 'features/auth/screens/splash_screen.dart';

class EcoTraceCollectorApp extends StatelessWidget {
  const EcoTraceCollectorApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'EcoTrace Collector',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      home: const SplashScreen(),
    );
  }
}
