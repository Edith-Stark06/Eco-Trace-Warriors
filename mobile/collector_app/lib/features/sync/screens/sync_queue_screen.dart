import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../../shared/widgets/empty_state.dart';
import '../../../shared/widgets/loading_indicator.dart';
import '../models/sync_queue_item.dart';
import '../providers/sync_providers.dart';

/// Lists every queued collector action (accept/start/complete taken while
/// offline or that failed to reach the backend), with per-item status and a
/// manual retry for anything that exhausted its automatic retries.
class SyncQueueScreen extends ConsumerWidget {
  const SyncQueueScreen({super.key, this.embedded = false});

  final bool embedded;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final items = ref.watch(syncQueueItemsProvider);

    final body = RefreshIndicator(
      onRefresh: () async {
        final manager = await ref.read(syncManagerProvider.future);
        await manager.drainQueue();
        ref.invalidate(syncQueueItemsProvider);
        ref.invalidate(pendingSyncCountProvider);
      },
      child: items.when(
        loading: () => const LoadingIndicator(),
        error: (error, _) => Center(child: Text('$error')),
        data: (queue) {
          if (queue.isEmpty) {
            return ListView(
              children: const [
                SizedBox(height: 48),
                EmptyState(
                  icon: Icons.cloud_done_outlined,
                  title: 'Everything is synced',
                  subtitle: 'Actions you take offline will queue here until connectivity returns.',
                ),
              ],
            );
          }
          return ListView.separated(
            padding: const EdgeInsets.all(16),
            itemCount: queue.length,
            separatorBuilder: (_, __) => const SizedBox(height: 8),
            itemBuilder: (context, index) => _QueueTile(item: queue[index]),
          );
        },
      ),
    );

    if (embedded) return body;
    return Scaffold(appBar: AppBar(title: const Text('Sync Queue')), body: body);
  }
}

class _QueueTile extends ConsumerWidget {
  const _QueueTile({required this.item});

  final SyncQueueItem item;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final (icon, color) = switch (item.status) {
      'pending' => (Icons.schedule, theme.colorScheme.outline),
      'syncing' => (Icons.sync, theme.colorScheme.primary),
      'failed' => (Icons.error_outline, theme.colorScheme.error),
      _ => (Icons.check_circle_outline, theme.colorScheme.primary),
    };

    return Card(
      child: ListTile(
        leading: Icon(icon, color: color),
        title: Text(item.actionLabel),
        subtitle: Text(
          item.errorMessage ??
              'Queued ${DateFormat.yMMMd().add_jm().format(item.createdAt.toLocal())}',
        ),
        trailing: item.status == 'failed'
            ? IconButton(
                icon: const Icon(Icons.refresh),
                tooltip: 'Retry now',
                onPressed: () async {
                  final repository = await ref.read(syncQueueRepositoryProvider.future);
                  await repository.retryFailed(item.id);
                  final manager = await ref.read(syncManagerProvider.future);
                  await manager.drainQueue();
                  ref.invalidate(syncQueueItemsProvider);
                  ref.invalidate(pendingSyncCountProvider);
                },
              )
            : null,
      ),
    );
  }
}
