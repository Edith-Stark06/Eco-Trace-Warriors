import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/utils/result.dart';
import '../../../shared/widgets/empty_state.dart';
import '../../../shared/widgets/error_state.dart';
import '../../../shared/widgets/loading_indicator.dart';
import '../models/submission.dart';
import '../providers/submissions_providers.dart';
import 'report_waste_screen.dart';
import 'submission_detail_screen.dart';

/// The consumer's own reports (`GET /submissions`, naturally scoped to "my
/// reports" — `findByUser` in `submission.service.ts`).
class SubmissionHistoryScreen extends ConsumerWidget {
  const SubmissionHistoryScreen({super.key, this.embedded = false});

  final bool embedded;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final submissions = ref.watch(submissionsProvider);

    final body = RefreshIndicator(
      onRefresh: () async => ref.invalidate(submissionsProvider),
      child: submissions.when(
        loading: () => const LoadingIndicator(),
        error: (error, _) => ListView(
          children: [
            const SizedBox(height: 48),
            ErrorState(
              failure: error is AppFailure ? error : AppFailure.unknown('$error'),
              onRetry: () => ref.invalidate(submissionsProvider),
            ),
          ],
        ),
        data: (items) {
          if (items.isEmpty) {
            return ListView(
              children: [
                const SizedBox(height: 48),
                const EmptyState(
                  icon: Icons.inventory_2_outlined,
                  title: 'No reports yet',
                  subtitle: 'Report your first e-waste pickup to see it here.',
                ),
              ],
            );
          }
          return ListView.separated(
            padding: const EdgeInsets.all(16),
            itemCount: items.length,
            separatorBuilder: (_, __) => const SizedBox(height: 8),
            itemBuilder: (context, index) => _SubmissionTile(submission: items[index]),
          );
        },
      ),
    );

    if (embedded) return body;
    return Scaffold(
      appBar: AppBar(title: const Text('My Reports')),
      body: body,
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => Navigator.of(context).push(
          MaterialPageRoute(builder: (_) => const ReportWasteScreen()),
        ),
        icon: const Icon(Icons.add),
        label: const Text('Report'),
      ),
    );
  }
}

class _SubmissionTile extends StatelessWidget {
  const _SubmissionTile({required this.submission});

  final Submission submission;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        title: Text(submission.category),
        subtitle: Text('${submission.estimatedWeight} kg — ${submission.address}'),
        trailing: Chip(label: Text(submission.status.label)),
        onTap: () => Navigator.of(context).push(
          MaterialPageRoute(builder: (_) => SubmissionDetailScreen(submissionId: submission.id)),
        ),
      ),
    );
  }
}
