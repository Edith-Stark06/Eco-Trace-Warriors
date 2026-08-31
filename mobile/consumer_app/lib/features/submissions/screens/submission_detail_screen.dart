import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../../core/utils/result.dart';
import '../../../shared/widgets/error_state.dart';
import '../../../shared/widgets/loading_indicator.dart';
import '../models/submission.dart';
import '../providers/submissions_providers.dart';

class SubmissionDetailScreen extends ConsumerWidget {
  const SubmissionDetailScreen({super.key, required this.submissionId});

  final String submissionId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final detail = ref.watch(submissionDetailProvider(submissionId));

    return Scaffold(
      appBar: AppBar(title: const Text('Report Details')),
      body: detail.when(
        loading: () => const LoadingIndicator(),
        error: (error, _) => ErrorState(
          failure: error is AppFailure ? error : AppFailure.unknown('$error'),
          onRetry: () => ref.invalidate(submissionDetailProvider(submissionId)),
        ),
        data: (submission) => _DetailBody(submission: submission),
      ),
    );
  }
}

class _DetailBody extends ConsumerWidget {
  const _DetailBody({required this.submission});

  final Submission submission;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final actionState = ref.watch(submissionActionControllerProvider);
    final dateFormat = DateFormat.yMMMd().add_jm();

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Row(
          children: [
            Expanded(child: Text(submission.category, style: theme.textTheme.headlineSmall)),
            Chip(label: Text(submission.status.label)),
          ],
        ),
        const SizedBox(height: 16),
        _Tile(icon: Icons.place_outlined, label: 'Pickup address', value: submission.address),
        _Tile(
          icon: Icons.scale_outlined,
          label: 'Estimated weight',
          value: '${submission.estimatedWeight} kg',
        ),
        if (submission.recoveredWeight != null)
          _Tile(
            icon: Icons.recycling,
            label: 'Recovered weight',
            value: '${submission.recoveredWeight} kg',
          ),
        if (submission.description != null && submission.description!.isNotEmpty)
          _Tile(icon: Icons.notes_outlined, label: 'Description', value: submission.description!),
        _Tile(
          icon: Icons.calendar_today_outlined,
          label: 'Submitted',
          value: dateFormat.format(submission.createdAt.toLocal()),
        ),
        if (submission.co2Saved != null)
          _Tile(
            icon: Icons.co2_outlined,
            label: 'CO2 avoided',
            value: '${submission.co2Saved!.toStringAsFixed(2)} kg',
          ),
        _Tile(
          icon: Icons.card_giftcard_outlined,
          label: 'Reward issued',
          value: submission.rewardIssued ? 'Yes' : 'Not yet',
        ),
        const SizedBox(height: 24),
        if (submission.isEditable)
          OutlinedButton.icon(
            onPressed: actionState.isLoading
                ? null
                : () async {
                    final confirmed = await showDialog<bool>(
                      context: context,
                      builder: (context) => AlertDialog(
                        title: const Text('Cancel this report?'),
                        content: const Text('This cannot be undone.'),
                        actions: [
                          TextButton(
                            onPressed: () => Navigator.of(context).pop(false),
                            child: const Text('Keep it'),
                          ),
                          TextButton(
                            onPressed: () => Navigator.of(context).pop(true),
                            child: const Text('Cancel report'),
                          ),
                        ],
                      ),
                    );
                    if (confirmed != true) return;
                    final ok = await ref
                        .read(submissionActionControllerProvider.notifier)
                        .cancel(submission.id);
                    if (!context.mounted) return;
                    if (ok) Navigator.of(context).pop();
                  },
            icon: const Icon(Icons.cancel_outlined),
            label: const Text('Cancel report'),
          )
        else
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 12),
            child: Text(
              'This report can no longer be edited or cancelled — '
              'it has already entered the pickup workflow.',
              style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.outline),
              textAlign: TextAlign.center,
            ),
          ),
      ],
    );
  }
}

class _Tile extends StatelessWidget {
  const _Tile({required this.icon, required this.label, required this.value});

  final IconData icon;
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 20, color: theme.colorScheme.outline),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, style: theme.textTheme.labelSmall
                    ?.copyWith(color: theme.colorScheme.outline)),
                Text(value, style: theme.textTheme.bodyMedium),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
