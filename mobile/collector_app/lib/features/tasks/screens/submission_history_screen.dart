import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../../core/utils/result.dart';
import '../../../shared/widgets/empty_state.dart';
import '../../../shared/widgets/error_state.dart';
import '../../../shared/widgets/loading_indicator.dart';
import '../models/submission.dart';
import '../providers/tasks_providers.dart';
import 'task_detail_screen.dart';

/// Shows every submission this device has locally cached (populated by the
/// active-assignments dashboard over time), most recent first.
///
/// This is deliberately **not** backed by a dedicated server-side history
/// endpoint — the backend's `SubmissionRepository.findByCollector` query
/// exists but is never wired to a route (`backend/src/modules/submission/`);
/// only `GET /collector/submissions` (active assignments) is exposed. See
/// `TasksRepository.cachedHistory` and `reports/P6_3_MOBILE_COLLECTOR.md`
/// for the full rationale — this screen is honest about that scope rather
/// than presenting a fabricated "complete history".
class SubmissionHistoryScreen extends ConsumerWidget {
  const SubmissionHistoryScreen({super.key, this.embedded = false});

  /// When true, renders without its own `Scaffold`/`AppBar` (embedded as a
  /// tab inside `HomeScreen`).
  final bool embedded;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final history = ref.watch(submissionHistoryProvider);

    final body = RefreshIndicator(
      onRefresh: () async => ref.invalidate(submissionHistoryProvider),
      child: history.when(
        loading: () => const LoadingIndicator(),
        error: (error, _) => ListView(
          children: [
            const SizedBox(height: 48),
            ErrorState(
              failure: error is AppFailure ? error : AppFailure.unknown('$error'),
              onRetry: () => ref.invalidate(submissionHistoryProvider),
            ),
          ],
        ),
        data: (submissions) {
          if (submissions.isEmpty) {
            return ListView(
              children: const [
                SizedBox(height: 48),
                EmptyState(
                  icon: Icons.inventory_2_outlined,
                  title: 'No pickup history yet',
                  subtitle: 'Submissions you have viewed or acted on will appear here.',
                ),
              ],
            );
          }
          return ListView.separated(
            padding: const EdgeInsets.all(16),
            itemCount: submissions.length,
            separatorBuilder: (_, __) => const SizedBox(height: 8),
            itemBuilder: (context, index) => _HistoryTile(submission: submissions[index]),
          );
        },
      ),
    );

    if (embedded) return body;
    return Scaffold(appBar: AppBar(title: const Text('Submission History')), body: body);
  }
}

class _HistoryTile extends StatelessWidget {
  const _HistoryTile({required this.submission});

  final Submission submission;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        title: Text(submission.category),
        subtitle: Text(
          '${submission.address}\n${DateFormat.yMMMd().format(submission.updatedAt.toLocal())}',
        ),
        isThreeLine: true,
        trailing: Chip(label: Text(submission.status.label)),
        onTap: () => Navigator.of(context).push(
          MaterialPageRoute(builder: (_) => TaskDetailScreen(submissionId: submission.id)),
        ),
      ),
    );
  }
}
