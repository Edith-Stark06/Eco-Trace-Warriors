import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/utils/result.dart';
import '../../../shared/widgets/empty_state.dart';
import '../../../shared/widgets/error_state.dart';
import '../../../shared/widgets/loading_indicator.dart';
import '../../../shared/widgets/network_status_banner.dart';
import '../../auth/providers/auth_providers.dart';
import '../../profile/screens/profile_screen.dart';
import '../../sync/providers/sync_providers.dart';
import '../../sync/screens/sync_queue_screen.dart';
import '../../tasks/models/submission.dart';
import '../../tasks/providers/tasks_providers.dart';
import '../../tasks/screens/submission_history_screen.dart';
import '../../tasks/screens/task_detail_screen.dart';

/// Home / task list: the collector's active assignments
/// (`GET /collector/submissions`). This doubles as the "Task List" screen
/// from the design brief — a separate screen would only duplicate this one.
class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});

  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen> {
  int _tabIndex = 0;

  @override
  void initState() {
    super.initState();
    // Registers the connectivity->drainQueue side effect for the app's
    // lifetime once a Home screen exists.
    ref.read(syncOnReconnectProvider);
  }

  @override
  Widget build(BuildContext context) {
    final screens = [
      _TaskListView(),
      const SubmissionHistoryScreen(embedded: true),
      const SyncQueueScreen(embedded: true),
      const ProfileScreen(embedded: true),
    ];

    return Scaffold(
      appBar: AppBar(title: const Text('EcoTrace Collector')),
      body: Column(
        children: [
          const NetworkStatusBanner(),
          Expanded(child: screens[_tabIndex]),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tabIndex,
        onDestinationSelected: (index) => setState(() => _tabIndex = index),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.list_alt), label: 'Tasks'),
          NavigationDestination(icon: Icon(Icons.history), label: 'History'),
          NavigationDestination(icon: Icon(Icons.sync), label: 'Sync'),
          NavigationDestination(icon: Icon(Icons.person), label: 'Profile'),
        ],
      ),
    );
  }
}

class _TaskListView extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final assignments = ref.watch(assignmentsProvider);
    final profile = ref.watch(authControllerProvider).profile;

    return RefreshIndicator(
      onRefresh: () async => ref.invalidate(assignmentsProvider),
      child: assignments.when(
        loading: () => const LoadingIndicator(message: 'Loading your assignments…'),
        error: (error, _) => ListView(
          children: [
            const SizedBox(height: 48),
            ErrorState(
              failure: error is AppFailure ? error : AppFailure.unknown('$error'),
              onRetry: () => ref.invalidate(assignmentsProvider),
            ),
          ],
        ),
        data: (submissions) {
          if (submissions.isEmpty) {
            return ListView(
              children: [
                const SizedBox(height: 48),
                EmptyState(
                  icon: Icons.task_alt,
                  title: profile != null ? 'No assignments right now, ${profile.fullName.split(' ').first}' : 'No assignments right now',
                  subtitle: 'New pickups assigned to you by a coordinator will appear here.',
                ),
              ],
            );
          }
          return ListView.separated(
            padding: const EdgeInsets.all(16),
            itemCount: submissions.length,
            separatorBuilder: (_, __) => const SizedBox(height: 12),
            itemBuilder: (context, index) => _TaskCard(submission: submissions[index]),
          );
        },
      ),
    );
  }
}

class _TaskCard extends StatelessWidget {
  const _TaskCard({required this.submission});

  final Submission submission;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: () => Navigator.of(context).push(
          MaterialPageRoute(builder: (_) => TaskDetailScreen(submissionId: submission.id)),
        ),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(submission.category, style: theme.textTheme.titleMedium),
                  ),
                  _StatusChip(status: submission.status),
                ],
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  Icon(Icons.place_outlined, size: 16, color: theme.colorScheme.outline),
                  const SizedBox(width: 4),
                  Expanded(
                    child: Text(
                      submission.address,
                      style: theme.textTheme.bodySmall,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 4),
              Row(
                children: [
                  Icon(Icons.scale_outlined, size: 16, color: theme.colorScheme.outline),
                  const SizedBox(width: 4),
                  Text('${submission.estimatedWeight} kg', style: theme.textTheme.bodySmall),
                ],
              ),
              if (submission.nextAction != null) ...[
                const SizedBox(height: 12),
                Align(
                  alignment: Alignment.centerRight,
                  child: Text(
                    'Tap for ${submission.nextAction!.label.toLowerCase()} →',
                    style: theme.textTheme.labelMedium?.copyWith(color: theme.colorScheme.primary),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _StatusChip extends StatelessWidget {
  const _StatusChip({required this.status});

  final SubmissionStatus status;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Chip(
      label: Text(status.label, style: theme.textTheme.labelSmall),
      visualDensity: VisualDensity.compact,
      materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
      padding: EdgeInsets.zero,
    );
  }
}
