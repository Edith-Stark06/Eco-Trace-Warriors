import 'package:flutter/material.dart';

import 'core/theme/app_theme.dart';
import 'features/auth/screens/splash_screen.dart';

class EcoTraceConsumerApp extends StatelessWidget {
  const EcoTraceConsumerApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'EcoTrace',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      home: const SplashScreen(),
    );
  }
}
