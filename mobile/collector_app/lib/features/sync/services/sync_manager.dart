import '../../../core/config/app_config.dart';
import '../../../core/diagnostics/app_logger.dart';
import '../../../core/utils/result.dart';
import '../../tasks/data/tasks_repository.dart';
import '../../tasks/models/submission.dart';
import '../data/sync_queue_repository.dart';
import '../models/sync_queue_item.dart';

/// Drains the local sync queue against the backend when connectivity is
/// available, and reconciles a stale replay against the submission's actual
/// current state instead of blindly treating "the transition failed because
/// it already happened" as an error.
///
/// Why reconciliation matters here specifically: `accept`/`start`/`complete`
/// are PATCH *state transitions*, not idempotent creates. If a queued
/// `accept` actually reached the server before the app went offline (the
/// response was simply never received), replaying it later will fail
/// server-side validation because the submission is no longer `ASSIGNED`.
/// Treating that failure as "already done" — by checking whether the
/// submission's current status is at or past this action's target — is what
/// keeps a retried action from either duplicating work or getting
/// permanently stuck as "failed" for something that, from the collector's
/// perspective, already succeeded.
class SyncManager {
  SyncManager({
    required SyncQueueRepository queueRepository,
    required TasksRepository tasksRepository,
  })  : _queueRepository = queueRepository,
        _tasksRepository = tasksRepository;

  final SyncQueueRepository _queueRepository;
  final TasksRepository _tasksRepository;

  bool _isSyncing = false;

  /// Performs an action immediately; on any failure, falls back to queuing
  /// it for later instead of losing the collector's tap. Returns the
  /// resulting submission on an immediate success, or `null` when queued.
  Future<Result<Submission?>> performOrQueue(
    Submission submission,
    SubmissionAction action,
  ) async {
    final result = await _tasksRepository.performAction(submission.id, action.path);
    return result.when(
      success: (updated) => Result.success(updated),
      failure: (failure) async {
        if (!failure.isRetryable) {
          return Result.failure(failure);
        }
        await _queueRepository.enqueue(
          submissionId: submission.id,
          actionPath: action.path,
          actionLabel: action.label,
        );
        return const Result.success(null);
      },
    );
  }

  /// Drains every pending queue item against the backend. Safe to call
  /// repeatedly/concurrently — a no-op re-entry while already draining.
  Future<void> drainQueue() async {
    if (_isSyncing) return;
    _isSyncing = true;
    try {
      final items = await _queueRepository.pendingItems();
      AppLogger.info('sync', 'Draining sync queue', context: {'pendingCount': items.length});
      for (final item in items) {
        await _syncOne(item);
      }
    } finally {
      _isSyncing = false;
    }
  }

  Future<void> _syncOne(SyncQueueItem item) async {
    await _queueRepository.updateItem(item.copyWith(status: 'syncing'));

    final result = await _tasksRepository.performAction(item.submissionId, item.actionPath);
    final resolved = await result.when(
      success: (_) async => true,
      failure: (failure) => _reconcileAgainstServerState(item, failure),
    );

    if (resolved) {
      AppLogger.info(
        'sync',
        'Queue item synced',
        context: {'submissionId': item.submissionId, 'action': item.actionPath},
      );
      await _queueRepository.remove(item.id);
      return;
    }

    final retryCount = item.retryCount + 1;
    final exhausted = retryCount >= AppConfig.maxSyncRetries;
    AppLogger.warn(
      'sync',
      exhausted ? 'Queue item failed permanently' : 'Queue item retry scheduled',
      context: {
        'submissionId': item.submissionId,
        'action': item.actionPath,
        'retryCount': retryCount,
      },
    );
    await _queueRepository.updateItem(
      item.copyWith(
        status: exhausted ? 'failed' : 'pending',
        retryCount: retryCount,
        lastAttemptAt: DateTime.now().toUtc(),
        errorMessage: exhausted
            ? 'Failed after $retryCount attempts. Tap to retry manually.'
            : 'Retrying…',
      ),
    );
  }

  /// Returns `true` if the submission's current server state shows this
  /// action already took effect (safe to drop from the queue), `false` if
  /// it should still be retried/marked failed.
  Future<bool> _reconcileAgainstServerState(SyncQueueItem item, AppFailure failure) async {
    if (failure.statusCode == null || failure.statusCode! < 400 || failure.statusCode! >= 500) {
      // Not a state-conflict-shaped failure (e.g. a genuine network error) —
      // nothing to reconcile, just retry normally.
      return false;
    }
    final current = await _tasksRepository.fetchById(item.submissionId);
    return current.when(
      success: (submission) => _actionAlreadyApplied(submission.status, item.actionPath),
      failure: (_) => false,
    );
  }

  /// Explicit membership checks rather than ordinal/`.index` comparisons —
  /// `SubmissionStatus.rejected` is a terminal *exception* state, not
  /// "further along" the happy path, so an ordinal `>=` comparison would
  /// wrongly treat a rejected submission as "already collected".
  bool _actionAlreadyApplied(SubmissionStatus status, String actionPath) {
    const pastAccept = {
      SubmissionStatus.accepted,
      SubmissionStatus.inProgress,
      SubmissionStatus.collected,
      SubmissionStatus.recycling,
      SubmissionStatus.recycled,
      SubmissionStatus.completed,
    };
    const pastStart = {
      SubmissionStatus.inProgress,
      SubmissionStatus.collected,
      SubmissionStatus.recycling,
      SubmissionStatus.recycled,
      SubmissionStatus.completed,
    };
    const pastComplete = {
      SubmissionStatus.collected,
      SubmissionStatus.recycling,
      SubmissionStatus.recycled,
      SubmissionStatus.completed,
    };
    return switch (actionPath) {
      'accept' => pastAccept.contains(status),
      'start' => pastStart.contains(status),
      'complete' => pastComplete.contains(status),
      _ => false,
    };
  }
}
