import 'package:ecotrace_collector/features/sync/models/sync_queue_item.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('SyncQueueItem row round trip', () {
    test('toRow -> fromRow preserves every field', () {
      final item = SyncQueueItem(
        id: 'queue-1',
        submissionId: 'sub-1',
        actionPath: 'accept',
        actionLabel: 'Accept pickup',
        status: 'pending',
        retryCount: 2,
        createdAt: DateTime.utc(2026, 1, 1, 12, 0, 0),
        lastAttemptAt: DateTime.utc(2026, 1, 1, 12, 5, 0),
        errorMessage: 'Retrying…',
      );

      final restored = SyncQueueItem.fromRow(item.toRow());

      expect(restored.id, item.id);
      expect(restored.submissionId, item.submissionId);
      expect(restored.actionPath, item.actionPath);
      expect(restored.status, item.status);
      expect(restored.retryCount, item.retryCount);
      expect(restored.createdAt, item.createdAt);
      expect(restored.lastAttemptAt, item.lastAttemptAt);
      expect(restored.errorMessage, item.errorMessage);
    });

    test('nullable fields round-trip as null', () {
      final item = SyncQueueItem(
        id: 'queue-2',
        submissionId: 'sub-2',
        actionPath: 'start',
        actionLabel: 'Start pickup',
        status: 'pending',
        retryCount: 0,
        createdAt: DateTime.utc(2026, 1, 1),
      );

      final restored = SyncQueueItem.fromRow(item.toRow());

      expect(restored.lastAttemptAt, isNull);
      expect(restored.errorMessage, isNull);
    });
  });

  group('SyncQueueItem.copyWith', () {
    test('clearError removes the error message even when a new one is not given', () {
      final item = SyncQueueItem(
        id: 'queue-3',
        submissionId: 'sub-3',
        actionPath: 'complete',
        actionLabel: 'Mark collected',
        status: 'failed',
        retryCount: 5,
        createdAt: DateTime.utc(2026, 1, 1),
        errorMessage: 'Failed after 5 attempts.',
      );

      final cleared = item.copyWith(status: 'pending', clearError: true);

      expect(cleared.errorMessage, isNull);
      expect(cleared.status, 'pending');
      expect(cleared.retryCount, 5); // untouched fields are preserved
    });
  });
}
