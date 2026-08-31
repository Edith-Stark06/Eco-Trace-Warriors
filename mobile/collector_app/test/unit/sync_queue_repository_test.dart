@TestOn('vm')
library;

import 'package:ecotrace_collector/core/storage/local_database.dart';
import 'package:ecotrace_collector/features/sync/data/sync_queue_repository.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

/// Uses `sqflite_common_ffi` to run real SQL against a real (in-memory)
/// SQLite database on the plain Dart test VM — no Android/iOS platform
/// channel, no mocking of the SQL layer itself. Requires the native
/// `sqlite3` shared library to be resolvable on the machine running
/// `flutter test` (the standard, documented requirement for this package;
/// see https://pub.dev/packages/sqflite_common_ffi). This could not be
/// executed in the environment P6.3 was authored in (no Flutter/Dart SDK —
/// see `reports/P6_3_MOBILE_COLLECTOR.md`), so treat it as written-but-unrun.
void main() {
  late LocalDatabase database;
  late SyncQueueRepository repository;

  setUpAll(() {
    sqfliteFfiInit();
  });

  setUp(() async {
    database = await LocalDatabase.openAt(inMemoryDatabasePath, factory: databaseFactoryFfi);
    repository = SyncQueueRepository(database);
  });

  tearDown(() async {
    await database.db.close();
  });

  test('enqueue persists a new pending item', () async {
    final item = await repository.enqueue(
      submissionId: 'sub-1',
      actionPath: 'accept',
      actionLabel: 'Accept pickup',
    );

    expect(item.status, 'pending');
    final pending = await repository.pendingItems();
    expect(pending, hasLength(1));
    expect(pending.single.submissionId, 'sub-1');
  });

  test('re-enqueuing the same submission+action replaces the row instead of duplicating', () async {
    await repository.enqueue(submissionId: 'sub-1', actionPath: 'accept', actionLabel: 'Accept pickup');
    await repository.enqueue(submissionId: 'sub-1', actionPath: 'accept', actionLabel: 'Accept pickup');

    final all = await repository.allItems();
    expect(all, hasLength(1), reason: 'a duplicate tap must not create a second queue row');
  });

  test('enqueuing a different action for the same submission adds a second row', () async {
    await repository.enqueue(submissionId: 'sub-1', actionPath: 'accept', actionLabel: 'Accept pickup');
    await repository.enqueue(submissionId: 'sub-1', actionPath: 'start', actionLabel: 'Start pickup');

    final all = await repository.allItems();
    expect(all, hasLength(2));
  });

  test('pendingCount excludes synced/failed items', () async {
    final item = await repository.enqueue(
      submissionId: 'sub-2',
      actionPath: 'start',
      actionLabel: 'Start pickup',
    );
    expect(await repository.pendingCount(), 1);

    await repository.remove(item.id);
    expect(await repository.pendingCount(), 0);
  });

  test('retryFailed resets a failed item back to pending and clears its error', () async {
    final item = await repository.enqueue(
      submissionId: 'sub-3',
      actionPath: 'complete',
      actionLabel: 'Mark collected',
    );
    await repository.updateItem(
      item.copyWith(status: 'failed', errorMessage: 'Failed after 5 attempts.'),
    );

    await repository.retryFailed(item.id);

    final all = await repository.allItems();
    expect(all.single.status, 'pending');
    expect(all.single.errorMessage, isNull);
  });
}
