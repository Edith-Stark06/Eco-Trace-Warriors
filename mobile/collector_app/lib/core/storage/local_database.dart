import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:sqflite/sqflite.dart';

import '../config/app_config.dart';

/// Local SQLite database backing the offline-first architecture.
///
/// Two tables:
/// - `sync_queue`: collector actions (accept/start/complete a pickup) taken
///   while offline, each keyed by a client-generated id
///   (`SyncQueueItem.id`) so `SyncQueueRepository.enqueue` can collapse a
///   re-tap of the same action on the same submission into one row instead
///   of duplicating it.
/// - `submission_cache`: a local mirror of submissions this collector has
///   seen (assigned/accepted/in-progress/history), so the task list and
///   submission-history screens render from cache when offline.
///
/// A thin wrapper, not an ORM — repositories own the SQL for their own
/// tables so the schema stays easy to reason about in one place per table.
class LocalDatabase {
  LocalDatabase._(this._db);

  final Database _db;

  static LocalDatabase? _instance;

  static Future<LocalDatabase> open() async {
    if (_instance != null) return _instance!;
    final directory = await getApplicationDocumentsDirectory();
    final path = p.join(directory.path, AppConfig.databaseName);
    _instance = await openAt(path);
    return _instance!;
  }

  /// Opens (creating if needed) the database at an explicit path — the
  /// path-resolution-free half of [open], factored out so tests can point
  /// it at an in-memory or temp-file database without mocking
  /// `path_provider`. Does not touch the [open] singleton.
  ///
  /// [factory] defaults to sqflite's platform [databaseFactory]; tests pass
  /// `sqflite_common_ffi`'s `databaseFactoryFfi` instead, which needs no
  /// Android/iOS platform channel (see `test/unit/sync_queue_repository_test.dart`).
  static Future<LocalDatabase> openAt(String path, {DatabaseFactory? factory}) async {
    final db = await (factory ?? databaseFactory).openDatabase(
      path,
      options: OpenDatabaseOptions(
        version: 1,
        onCreate: (db, version) async {
          await db.execute('''
            CREATE TABLE sync_queue (
              id TEXT PRIMARY KEY,
              submission_id TEXT NOT NULL,
              action_path TEXT NOT NULL,
              action_label TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'pending',
              retry_count INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL,
              last_attempt_at TEXT,
              error_message TEXT
            )
          ''');
          await db.execute('''
            CREATE TABLE submission_cache (
              id TEXT PRIMARY KEY,
              status TEXT NOT NULL,
              synced_at TEXT NOT NULL,
              raw_json TEXT NOT NULL
            )
          ''');
          await db.execute('CREATE INDEX idx_sync_queue_status ON sync_queue(status)');
          await db.execute('CREATE INDEX idx_submission_cache_status ON submission_cache(status)');
        },
      ),
    );
    return LocalDatabase._(db);
  }

  Database get db => _db;

  /// Test-only: reset the singleton so a fresh in-memory/temp database can
  /// be opened for the next test.
  static void resetForTesting() {
    _instance = null;
  }
}
