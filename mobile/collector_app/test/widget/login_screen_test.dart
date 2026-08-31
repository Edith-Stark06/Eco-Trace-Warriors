import 'package:ecotrace_collector/features/auth/screens/login_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  Widget wrap(Widget child) {
    return ProviderScope(child: MaterialApp(home: child));
  }

  testWidgets('shows validation errors when submitting an empty form', (tester) async {
    await tester.pumpWidget(wrap(const LoginScreen()));

    await tester.tap(find.widgetWithText(ElevatedButton, 'Sign in'));
    await tester.pump();

    expect(find.text('Email is required'), findsOneWidget);
    expect(find.text('Password is required'), findsOneWidget);
  });

  testWidgets('shows a validation error for a malformed email', (tester) async {
    await tester.pumpWidget(wrap(const LoginScreen()));

    await tester.enterText(find.byType(TextFormField).first, 'not-an-email');
    await tester.tap(find.widgetWithText(ElevatedButton, 'Sign in'));
    await tester.pump();

    expect(find.text('Enter a valid email address'), findsOneWidget);
  });

  testWidgets('toggles password visibility', (tester) async {
    await tester.pumpWidget(wrap(const LoginScreen()));

    expect(find.byIcon(Icons.visibility), findsOneWidget);
    await tester.tap(find.byIcon(Icons.visibility));
    await tester.pump();
    expect(find.byIcon(Icons.visibility_off), findsOneWidget);
  });

  testWidgets('shows the collector-access info dialog, not a functional register form', (tester) async {
    await tester.pumpWidget(wrap(const LoginScreen()));

    await tester.tap(find.text("Don't have a collector account?"));
    await tester.pumpAndSettle();

    expect(find.text('Requesting collector access'), findsOneWidget);
    expect(find.textContaining('provisioned by your regional EcoTrace'), findsOneWidget);
  });
}
