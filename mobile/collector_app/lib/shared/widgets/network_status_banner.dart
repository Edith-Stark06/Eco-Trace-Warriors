import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../features/sync/providers/sync_providers.dart';

/// A thin banner shown at the top of screens when the device is offline or
/// has pending queued submissions — gives the collector constant visibility
/// into sync state without needing to visit the Sync Queue screen.
class NetworkStatusBanner extends ConsumerWidget {
  const NetworkStatusBanner({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isOnline = ref.watch(connectivityProvider).value ?? true;
    final pendingCount = ref.watch(pendingSyncCountProvider).value ?? 0;

    if (isOnline && pendingCount == 0) {
      return const SizedBox.shrink();
    }

    final theme = Theme.of(context);
    final String message;
    final Color background;
    final IconData icon;

    if (!isOnline) {
      message = pendingCount > 0
          ? 'Offline — $pendingCount submission${pendingCount == 1 ? '' : 's'} queued'
          : 'Offline — submissions will queue locally';
      background = theme.colorScheme.errorContainer;
      icon = Icons.cloud_off;
    } else {
      message = 'Syncing $pendingCount pending submission${pendingCount == 1 ? '' : 's'}…';
      background = theme.colorScheme.secondaryContainer;
      icon = Icons.cloud_sync;
    }

    return Container(
      width: double.infinity,
      color: background,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Row(
        children: [
          Icon(icon, size: 18),
          const SizedBox(width: 8),
          Expanded(child: Text(message, style: theme.textTheme.bodySmall)),
        ],
      ),
    );
  }
}
