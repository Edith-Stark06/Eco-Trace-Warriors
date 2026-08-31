/// A queued collector action (accept/start/complete) waiting to reach the
/// backend, persisted locally so it survives app restarts while offline.
class SyncQueueItem {
  const SyncQueueItem({
    required this.id,
    required this.submissionId,
    required this.actionPath,
    required this.actionLabel,
    required this.status,
    required this.retryCount,
    required this.createdAt,
    this.lastAttemptAt,
    this.errorMessage,
  });

  /// Client-generated id (uuid) — also doubles as the idempotency marker:
  /// re-queuing the same action for the same submission replaces the
  /// existing row rather than duplicating it (see `SyncQueueRepository.enqueue`).
  final String id;
  final String submissionId;

  /// `accept` | `start` | `complete` — matches `SubmissionAction.path`.
  final String actionPath;
  final String actionLabel;

  /// `pending` | `syncing` | `synced` | `failed`.
  final String status;
  final int retryCount;
  final DateTime createdAt;
  final DateTime? lastAttemptAt;
  final String? errorMessage;

  SyncQueueItem copyWith({
    String? status,
    int? retryCount,
    DateTime? lastAttemptAt,
    String? errorMessage,
    bool clearError = false,
  }) {
    return SyncQueueItem(
      id: id,
      submissionId: submissionId,
      actionPath: actionPath,
      actionLabel: actionLabel,
      status: status ?? this.status,
      retryCount: retryCount ?? this.retryCount,
      createdAt: createdAt,
      lastAttemptAt: lastAttemptAt ?? this.lastAttemptAt,
      errorMessage: clearError ? null : (errorMessage ?? this.errorMessage),
    );
  }

  Map<String, dynamic> toRow() {
    return {
      'id': id,
      'submission_id': submissionId,
      'action_path': actionPath,
      'action_label': actionLabel,
      'status': status,
      'retry_count': retryCount,
      'created_at': createdAt.toIso8601String(),
      'last_attempt_at': lastAttemptAt?.toIso8601String(),
      'error_message': errorMessage,
    };
  }

  factory SyncQueueItem.fromRow(Map<String, dynamic> row) {
    return SyncQueueItem(
      id: row['id'] as String,
      submissionId: row['submission_id'] as String,
      actionPath: row['action_path'] as String,
      actionLabel: row['action_label'] as String,
      status: row['status'] as String,
      retryCount: row['retry_count'] as int,
      createdAt: DateTime.parse(row['created_at'] as String),
      lastAttemptAt:
          row['last_attempt_at'] != null ? DateTime.parse(row['last_attempt_at'] as String) : null,
      errorMessage: row['error_message'] as String?,
    );
  }
}
