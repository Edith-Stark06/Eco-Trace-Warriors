import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/utils/result.dart';
import '../../sync/providers/sync_providers.dart';
import '../models/submission.dart';

/// The collector's active assignments (`GET /collector/submissions`,
/// cached offline). Refresh with `ref.invalidate(assignmentsProvider)`.
final assignmentsProvider = FutureProvider<List<Submission>>((ref) async {
  final repository = await ref.watch(tasksRepositoryProvider.future);
  final result = await repository.fetchAssignments();
  return result.when(
    success: (items) => items,
    failure: (failure) => throw failure,
  );
});

/// Resolves one submission by id from the local cache. Ensures the cache is
/// warm by waiting on `assignmentsProvider` first — see
/// `TasksRepository.fetchById`'s doc comment for why this never calls
/// `GET /submissions/:id` directly (collectors are not authorized to).
final submissionDetailProvider =
    FutureProvider.family<Submission, String>((ref, submissionId) async {
  await ref.watch(assignmentsProvider.future);
  final repository = await ref.watch(tasksRepositoryProvider.future);
  final result = await repository.fetchById(submissionId);
  return result.when(
    success: (submission) => submission,
    failure: (failure) => throw failure,
  );
});

/// Every submission this device has locally cached, most recent first —
/// backs the Submission History screen (see `TasksRepository.cachedHistory`
/// for why this is cache-only, not a server-side history call).
final submissionHistoryProvider = FutureProvider<List<Submission>>((ref) async {
  final repository = await ref.watch(tasksRepositoryProvider.future);
  return repository.cachedHistory();
});

/// Drives the accept/start/complete buttons: performs the action online, or
/// queues it for later, then refreshes the task list either way.
class TaskActionController extends Notifier<AsyncValue<void>> {
  @override
  AsyncValue<void> build() => const AsyncValue.data(null);

  Future<AppFailure?> perform(Submission submission, SubmissionAction action) async {
    state = const AsyncValue.loading();
    final syncManager = await ref.read(syncManagerProvider.future);
    final result = await syncManager.performOrQueue(submission, action);

    return result.when(
      success: (_) {
        state = const AsyncValue.data(null);
        ref.invalidate(assignmentsProvider);
        ref.invalidate(submissionDetailProvider(submission.id));
        ref.invalidate(pendingSyncCountProvider);
        return null;
      },
      failure: (failure) {
        state = AsyncValue.error(failure, StackTrace.current);
        return failure;
      },
    );
  }
}

final taskActionControllerProvider =
    NotifierProvider<TaskActionController, AsyncValue<void>>(TaskActionController.new);
