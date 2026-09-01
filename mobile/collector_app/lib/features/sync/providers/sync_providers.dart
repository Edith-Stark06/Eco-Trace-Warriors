import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/diagnostics/app_logger.dart';
import '../../../core/storage/local_database.dart';
import '../../auth/providers/auth_providers.dart';
import '../../tasks/data/tasks_repository.dart';
import '../data/sync_queue_repository.dart';
import '../models/sync_queue_item.dart';
import '../services/sync_manager.dart';

final localDatabaseProvider = FutureProvider<LocalDatabase>((ref) {
  return LocalDatabase.open();
});

final syncQueueRepositoryProvider = FutureProvider<SyncQueueRepository>((ref) async {
  final database = await ref.watch(localDatabaseProvider.future);
  return SyncQueueRepository(database);
});

final tasksRepositoryProvider = FutureProvider<TasksRepository>((ref) async {
  final database = await ref.watch(localDatabaseProvider.future);
  return TasksRepository(apiClient: ref.watch(apiClientProvider), database: database);
});

final syncManagerProvider = FutureProvider<SyncManager>((ref) async {
  final queueRepository = await ref.watch(syncQueueRepositoryProvider.future);
  final tasksRepository = await ref.watch(tasksRepositoryProvider.future);
  return SyncManager(queueRepository: queueRepository, tasksRepository: tasksRepository);
});

/// Live online/offline status. `true` when at least one non-none
/// connectivity result is reported (Wi-Fi, mobile data, ethernet, …).
final connectivityProvider = StreamProvider<bool>((ref) {
  return Connectivity()
      .onConnectivityChanged
      .map((results) => results.any((r) => r != ConnectivityResult.none));
});

/// Re-drains the sync queue whenever connectivity transitions to online.
final syncOnReconnectProvider = Provider<void>((ref) {
  ref.listen<AsyncValue<bool>>(connectivityProvider, (previous, next) {
    final isOnlineNow = next.value == true;
    if (previous?.value != next.value) {
      AppLogger.info('connectivity', isOnlineNow ? 'Online' : 'Offline');
    }
    final wasOffline = previous?.value == false;
    if (wasOffline && isOnlineNow) {
      ref.read(syncManagerProvider.future).then((manager) => manager.drainQueue());
    }
  });
});

/// Number of queue items still pending/syncing — drives the network status
/// banner and the sync-queue badge.
final pendingSyncCountProvider = FutureProvider<int>((ref) async {
  final repository = await ref.watch(syncQueueRepositoryProvider.future);
  return repository.pendingCount();
});

final syncQueueItemsProvider = FutureProvider<List<SyncQueueItem>>((ref) async {
  final repository = await ref.watch(syncQueueRepositoryProvider.future);
  return repository.allItems();
});
