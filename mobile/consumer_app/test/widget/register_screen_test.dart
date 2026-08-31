import 'package:ecotrace_consumer/features/auth/screens/register_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  Widget wrap(Widget child) => ProviderScope(child: MaterialApp(home: child));

  testWidgets('shows validation errors when submitting an empty form', (tester) async {
    await tester.pumpWidget(wrap(const RegisterScreen()));

    await tester.tap(find.widgetWithText(ElevatedButton, 'Create account'));
    await tester.pump();

    expect(find.text('Full name must be at least 2 characters'), findsOneWidget);
    expect(find.text('Email is required'), findsOneWidget);
    expect(find.text('Password must be at least 8 characters'), findsOneWidget);
  });

  testWidgets('flags mismatched passwords', (tester) async {
    await tester.pumpWidget(wrap(const RegisterScreen()));

    await tester.enterText(find.widgetWithText(TextFormField, 'Full name'), 'Jane Doe');
    await tester.enterText(find.widgetWithText(TextFormField, 'Email'), 'jane@example.com');
    await tester.enterText(find.widgetWithText(TextFormField, 'Password'), 'password123');
    await tester.enterText(find.widgetWithText(TextFormField, 'Confirm password'), 'different123');

    await tester.tap(find.widgetWithText(ElevatedButton, 'Create account'));
    await tester.pump();

    expect(find.text('Passwords do not match'), findsOneWidget);
  });
}
