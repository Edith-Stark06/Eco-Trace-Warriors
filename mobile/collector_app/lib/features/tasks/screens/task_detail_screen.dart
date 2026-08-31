import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../../core/utils/result.dart';
import '../../../shared/widgets/error_state.dart';
import '../../../shared/widgets/loading_indicator.dart';
import '../models/submission.dart';
import '../providers/tasks_providers.dart';

class TaskDetailScreen extends ConsumerWidget {
  const TaskDetailScreen({super.key, required this.submissionId});

  final String submissionId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final detail = ref.watch(submissionDetailProvider(submissionId));

    return Scaffold(
      appBar: AppBar(title: const Text('Pickup Details')),
      body: detail.when(
        loading: () => const LoadingIndicator(),
        error: (error, _) => ErrorState(
          failure: error is AppFailure ? error : AppFailure.unknown('$error'),
          onRetry: () => ref.invalidate(submissionDetailProvider(submissionId)),
        ),
        data: (submission) => _TaskDetailBody(submission: submission),
      ),
    );
  }
}

class _TaskDetailBody extends ConsumerWidget {
  const _TaskDetailBody({required this.submission});

  final Submission submission;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final actionState = ref.watch(taskActionControllerProvider);
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
        _DetailTile(icon: Icons.place_outlined, label: 'Pickup address', value: submission.address),
        _DetailTile(
          icon: Icons.my_location,
          label: 'Coordinates',
          value: '${submission.latitude.toStringAsFixed(5)}, '
              '${submission.longitude.toStringAsFixed(5)}',
        ),
        _DetailTile(
          icon: Icons.scale_outlined,
          label: 'Estimated weight',
          value: '${submission.estimatedWeight} kg',
        ),
        if (submission.description != null && submission.description!.isNotEmpty)
          _DetailTile(
            icon: Icons.notes_outlined,
            label: 'Notes from the consumer',
            value: submission.description!,
          ),
        _DetailTile(
          icon: Icons.calendar_today_outlined,
          label: 'Submitted',
          value: dateFormat.format(submission.createdAt.toLocal()),
        ),
        if (submission.imageUrls.isNotEmpty) ...[
          const SizedBox(height: 8),
          Text('Photos', style: theme.textTheme.titleSmall),
          const SizedBox(height: 8),
          SizedBox(
            height: 96,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              itemCount: submission.imageUrls.length,
              separatorBuilder: (_, __) => const SizedBox(width: 8),
              itemBuilder: (context, index) => ClipRRect(
                borderRadius: BorderRadius.circular(12),
                child: Image.network(
                  submission.imageUrls[index],
                  width: 96,
                  height: 96,
                  fit: BoxFit.cover,
                  errorBuilder: (context, error, stackTrace) => Container(
                    width: 96,
                    height: 96,
                    color: theme.colorScheme.surfaceContainerHighest,
                    child: const Icon(Icons.broken_image_outlined),
                  ),
                ),
              ),
            ),
          ),
        ],
        const SizedBox(height: 32),
        if (submission.nextAction != null)
          FilledButton.icon(
            onPressed: actionState.isLoading
                ? null
                : () async {
                    final failure = await ref
                        .read(taskActionControllerProvider.notifier)
                        .perform(submission, submission.nextAction!);
                    if (!context.mounted) return;
                    final message = failure != null
                        ? failure.message
                        : '${submission.nextAction!.label} recorded.';
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
                  },
            icon: actionState.isLoading
                ? const SizedBox(
                    height: 16,
                    width: 16,
                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                  )
                : const Icon(Icons.check_circle_outline),
            label: Text(submission.nextAction!.label),
          )
        else
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 12),
            child: Text(
              'No action available — this pickup is ${submission.status.label.toLowerCase()}.',
              style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.outline),
              textAlign: TextAlign.center,
            ),
          ),
      ],
    );
  }
}

class _DetailTile extends StatelessWidget {
  const _DetailTile({required this.icon, required this.label, required this.value});

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
