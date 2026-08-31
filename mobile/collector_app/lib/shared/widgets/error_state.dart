import 'package:flutter/material.dart';

import '../../core/utils/result.dart';

/// Reusable error display with an optional retry action.
///
/// Every screen that can fail (network error, API error) renders its
/// failure through this widget rather than a bespoke error UI, so retry
/// affordance and messaging stay consistent app-wide.
class ErrorState extends StatelessWidget {
  const ErrorState({super.key, required this.failure, this.onRetry});

  final AppFailure failure;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.error_outline, size: 56, color: theme.colorScheme.error),
            const SizedBox(height: 16),
            Text(
              failure.message,
              style: theme.textTheme.titleMedium,
              textAlign: TextAlign.center,
            ),
            if (failure.code != null) ...[
              const SizedBox(height: 4),
              Text(
                failure.code!,
                style: theme.textTheme.bodySmall
                    ?.copyWith(color: theme.colorScheme.outline),
              ),
            ],
            if (onRetry != null && failure.isRetryable) ...[
              const SizedBox(height: 20),
              FilledButton.icon(
                onPressed: onRetry,
                icon: const Icon(Icons.refresh),
                label: const Text('Try again'),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
