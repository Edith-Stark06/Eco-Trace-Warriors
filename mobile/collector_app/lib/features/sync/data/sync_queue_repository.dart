import 'package:uuid/uuid.dart';

import '../../../core/storage/local_database.dart';
import '../models/sync_queue_item.dart';

/// Persists queued collector actions in `sync_queue` (SQLite).
///
/// Deduplicates by `(submission_id, action_path)`: re-tapping the same
/// action on the same submission (e.g. the collector taps "Accept" twice
/// before connectivity returns) replaces the existing pending row instead of
/// enqueuing a duplicate — this is the client-side half of "avoid duplicate
/// submissions"; the server-side half is that these are PATCH state
/// transitions, not creates (see `SyncManager` for how a stale/duplicate
/// replay is reconciled against the server's actual current state).
class SyncQueueRepository {
  SyncQueueRepository(this._database);

  final LocalDatabase _database;
  static const _uuid = Uuid();

  Future<SyncQueueItem> enqueue({
    required String submissionId,
    required String actionPath,
    required String actionLabel,
  }) async {
    final existing = await _database.db.query(
      'sync_queue',
      where: 'submission_id = ? AND action_path = ? AND status IN (?, ?)',
      whereArgs: [submissionId, actionPath, 'pending', 'failed'],
    );
    if (existing.isNotEmpty) {
      final item = SyncQueueItem.fromRow(existing.first).copyWith(
        status: 'pending',
        clearError: true,
      );
      await _database.db.update(
        'sync_queue',
        item.toRow(),
        where: 'id = ?',
        whereArgs: [item.id],
      );
      return item;
    }

    final item = SyncQueueItem(
      id: _uuid.v4(),
      submissionId: submissionId,
      actionPath: actionPath,
      actionLabel: actionLabel,
      status: 'pending',
      retryCount: 0,
      createdAt: DateTime.now().toUtc(),
    );
    await _database.db.insert('sync_queue', item.toRow());
    return item;
  }

  Future<List<SyncQueueItem>> pendingItems() async {
    final rows = await _database.db.query(
      'sync_queue',
      where: 'status IN (?, ?)',
      whereArgs: ['pending', 'syncing'],
      orderBy: 'created_at ASC',
    );
    return rows.map(SyncQueueItem.fromRow).toList(growable: false);
  }

  Future<List<SyncQueueItem>> allItems() async {
    final rows = await _database.db.query('sync_queue', orderBy: 'created_at DESC');
    return rows.map(SyncQueueItem.fromRow).toList(growable: false);
  }

  Future<int> pendingCount() async {
    final result = await _database.db.rawQuery(
      "SELECT COUNT(*) as count FROM sync_queue WHERE status IN ('pending', 'syncing')",
    );
    return (result.first['count'] as int?) ?? 0;
  }

  Future<void> updateItem(SyncQueueItem item) async {
    await _database.db.update(
      'sync_queue',
      item.toRow(),
      where: 'id = ?',
      whereArgs: [item.id],
    );
  }

  Future<void> remove(String id) async {
    await _database.db.delete('sync_queue', where: 'id = ?', whereArgs: [id]);
  }

  Future<void> retryFailed(String id) async {
    await _database.db.update(
      'sync_queue',
      {'status': 'pending', 'error_message': null},
      where: 'id = ?',
      whereArgs: [id],
    );
  }
}
