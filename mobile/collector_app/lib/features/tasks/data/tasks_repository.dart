import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:sqflite/sqflite.dart';

import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/storage/local_database.dart';
import '../../../core/utils/result.dart';
import '../models/submission.dart';

/// Talks to the real `backend/` submission module's collector-workflow
/// endpoints (`backend/src/modules/submission/submission.routes.ts`):
/// `GET /collector/submissions`, `GET /submissions/:id`,
/// `PATCH /submissions/:id/{accept,start,complete}`.
///
/// Every read caches into `submission_cache` (SQLite) so the task list and
/// detail screens still render the collector's last known state offline;
/// every write goes through here directly when online, or is queued by
/// `SyncManager`/`SyncQueueRepository` when not.
class TasksRepository {
  TasksRepository({required ApiClient apiClient, required LocalDatabase database})
      : _apiClient = apiClient,
        _database = database;

  final ApiClient _apiClient;
  final LocalDatabase _database;

  /// The collector's active assignments (`GET /collector/submissions`).
  /// Falls back to the local cache on a network failure.
  Future<Result<List<Submission>>> fetchAssignments() async {
    try {
      final response = await _apiClient.get('/collector/submissions');
      final items = ((response.data as Map<String, dynamic>)['data'] as List<dynamic>)
          .map((e) => Submission.fromJson(e as Map<String, dynamic>))
          .toList(growable: false);
      await _cacheAll(items);
      return Result.success(items);
    } on DioException catch (e) {
      final cached = await _cachedAssignments();
      if (cached.isNotEmpty) {
        return Result.success(cached);
      }
      return Result.failure(mapDioExceptionToFailure(e));
    }
  }

  /// Resolves a submission by id from the **local cache only**.
  ///
  /// There is deliberately no `GET /submissions/:id` call here: that route's
  /// service-layer access check (`loadAccessible` in
  /// `backend/src/modules/submission/submission.service.ts`) only allows the
  /// submission's owning consumer or an admin — a collector fetching a
  /// pickup assigned to them (but not created by them) gets `404 Not Found`.
  /// Collectors only ever see submissions through `GET /collector/submissions`
  /// (`fetchAssignments`, cache-populating); this reads that cache back by
  /// id, so it only resolves for a submission the collector has actually
  /// been shown. Callers should ensure `fetchAssignments()` has populated the
  /// cache (or call it first) before relying on this for a fresh id.
  Future<Result<Submission>> fetchById(String submissionId) async {
    final cached = await _cachedById(submissionId);
    if (cached != null) return Result.success(cached);
    return const Result.failure(
      AppFailure(
        message: 'This pickup is not in your cached assignments. Pull to refresh your task list.',
        code: 'NOT_IN_CACHE',
        isRetryable: false,
      ),
    );
  }

  /// All submissions this collector has ever been assigned that this device
  /// has locally cached — i.e. history "as far as this device has seen",
  /// not a full server-side history. See `reports/P6_3_MOBILE_COLLECTOR.md`
  /// for why: the backend repository has a `findByCollector` (all-history)
  /// query (`submission.repository.ts`) that is never wired to any route —
  /// only the active-assignments dashboard is exposed. Building a fabricated
  /// "history" screen against an endpoint that doesn't exist would violate
  /// the explicit "do not invent backend behavior" instruction; this is the
  /// honest alternative using only what the backend actually serves.
  Future<List<Submission>> cachedHistory() async {
    final rows = await _database.db.query('submission_cache', orderBy: 'synced_at DESC');
    return rows
        .map((row) => Submission.fromJson(jsonDecode(row['raw_json'] as String) as Map<String, dynamic>))
        .toList(growable: false);
  }

  /// Submits a state-transition action (`accept`/`start`/`complete`)
  /// directly against the API. Callers on an unreliable connection should
  /// prefer `SyncManager.performOrQueue` instead, which falls back to the
  /// local queue on failure.
  Future<Result<Submission>> performAction(String submissionId, String actionPath) async {
    try {
      final response = await _apiClient.patch('/submissions/$submissionId/$actionPath');
      final submission =
          Submission.fromJson((response.data as Map<String, dynamic>)['data'] as Map<String, dynamic>);
      await _cacheAll([submission]);
      return Result.success(submission);
    } on DioException catch (e) {
      return Result.failure(mapDioExceptionToFailure(e));
    }
  }

  Future<List<Submission>> _cachedAssignments() async {
    final rows = await _database.db.query(
      'submission_cache',
      where: "status IN ('ASSIGNED', 'ACCEPTED', 'IN_PROGRESS')",
      orderBy: 'synced_at DESC',
    );
    return rows
        .map((row) => Submission.fromJson(jsonDecode(row['raw_json'] as String) as Map<String, dynamic>))
        .toList(growable: false);
  }

  Future<Submission?> _cachedById(String submissionId) async {
    final rows = await _database.db.query(
      'submission_cache',
      where: 'id = ?',
      whereArgs: [submissionId],
      limit: 1,
    );
    if (rows.isEmpty) return null;
    return Submission.fromJson(jsonDecode(rows.first['raw_json'] as String) as Map<String, dynamic>);
  }

  Future<void> _cacheAll(List<Submission> submissions) async {
    final batch = _database.db.batch();
    for (final submission in submissions) {
      batch.insert(
        'submission_cache',
        {
          'id': submission.id,
          'status': _statusWire(submission.status),
          'synced_at': DateTime.now().toUtc().toIso8601String(),
          'raw_json': jsonEncode(_toJson(submission)),
        },
        conflictAlgorithm: ConflictAlgorithm.replace,
      );
    }
    await batch.commit(noResult: true);
  }

  /// Inverse of `SubmissionStatus.fromWire` — explicit, not derived via
  /// string transformation, so it can't silently drift from the enum values
  /// the backend actually sends (`backend/prisma/schema.prisma`).
  String _statusWire(SubmissionStatus status) => switch (status) {
        SubmissionStatus.pending => 'PENDING',
        SubmissionStatus.assigned => 'ASSIGNED',
        SubmissionStatus.accepted => 'ACCEPTED',
        SubmissionStatus.inProgress => 'IN_PROGRESS',
        SubmissionStatus.collected => 'COLLECTED',
        SubmissionStatus.recycling => 'RECYCLING',
        SubmissionStatus.recycled => 'RECYCLED',
        SubmissionStatus.completed => 'COMPLETED',
        SubmissionStatus.rejected => 'REJECTED',
      };

  Map<String, dynamic> _toJson(Submission submission) {
    return {
      'id': submission.id,
      'userId': submission.userId,
      'category': submission.category,
      'description': submission.description,
      'estimatedWeight': submission.estimatedWeight,
      'address': submission.address,
      'latitude': submission.latitude,
      'longitude': submission.longitude,
      'imageUrls': submission.imageUrls,
      'status': _statusWire(submission.status),
      'assignedCollectorId': submission.assignedCollectorId,
      'pickupScheduledAt': submission.pickupScheduledAt?.toIso8601String(),
      'completedAt': submission.completedAt?.toIso8601String(),
      'createdAt': submission.createdAt.toIso8601String(),
      'updatedAt': submission.updatedAt.toIso8601String(),
    };
  }
}
