import 'package:flutter/material.dart';

/// Shared visual language for the Collector app.
///
/// A single source of truth for colors/typography so screens don't
/// hard-code styling — keeps the "reusable widgets, small screens" rule
/// from the mobile design requirements easy to follow.
class AppTheme {
  const AppTheme._();

  static const Color primaryGreen = Color(0xFF1B7A43);
  static const Color accentAmber = Color(0xFFE8A33D);
  static const Color errorRed = Color(0xFFB3261E);
  static const Color surfaceGray = Color(0xFFF5F6F3);

  static ThemeData light() {
    final colorScheme = ColorScheme.fromSeed(
      seedColor: primaryGreen,
      brightness: Brightness.light,
      error: errorRed,
    );
    return ThemeData(
      useMaterial3: true,
      colorScheme: colorScheme,
      scaffoldBackgroundColor: surfaceGray,
      appBarTheme: AppBarTheme(
        backgroundColor: colorScheme.surface,
        foregroundColor: colorScheme.onSurface,
        elevation: 0,
        centerTitle: false,
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 20),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
        filled: true,
        fillColor: colorScheme.surface,
      ),
      cardTheme: CardThemeData(
        elevation: 0,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        color: colorScheme.surface,
      ),
    );
  }
}
