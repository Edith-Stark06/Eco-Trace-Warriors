/// Mirrors `PublicSubmission`
/// (`backend/src/modules/submission/submission.types.ts`) and the
/// `SubmissionStatus` enum (`backend/prisma/schema.prisma`) field-for-field.
enum SubmissionStatus {
  pending,
  assigned,
  accepted,
  inProgress,
  collected,
  recycling,
  recycled,
  completed,
  rejected;

  static SubmissionStatus fromWire(String value) {
    return switch (value) {
      'PENDING' => SubmissionStatus.pending,
      'ASSIGNED' => SubmissionStatus.assigned,
      'ACCEPTED' => SubmissionStatus.accepted,
      'IN_PROGRESS' => SubmissionStatus.inProgress,
      'COLLECTED' => SubmissionStatus.collected,
      'RECYCLING' => SubmissionStatus.recycling,
      'RECYCLED' => SubmissionStatus.recycled,
      'COMPLETED' => SubmissionStatus.completed,
      'REJECTED' => SubmissionStatus.rejected,
      _ => throw ArgumentError('Unknown submission status: $value'),
    };
  }

  /// Human-readable label for the task-list / detail UI.
  String get label => switch (this) {
        SubmissionStatus.pending => 'Pending assignment',
        SubmissionStatus.assigned => 'Assigned to you',
        SubmissionStatus.accepted => 'Accepted',
        SubmissionStatus.inProgress => 'Pickup in progress',
        SubmissionStatus.collected => 'Collected',
        SubmissionStatus.recycling => 'Recycling',
        SubmissionStatus.recycled => 'Recycled',
        SubmissionStatus.completed => 'Completed',
        SubmissionStatus.rejected => 'Rejected',
      };
}

/// A waste-collection submission (mirrors `PublicSubmission`).
class Submission {
  const Submission({
    required this.id,
    required this.userId,
    required this.category,
    required this.description,
    required this.estimatedWeight,
    required this.address,
    required this.latitude,
    required this.longitude,
    required this.imageUrls,
    required this.status,
    required this.assignedCollectorId,
    required this.pickupScheduledAt,
    required this.completedAt,
    required this.createdAt,
    required this.updatedAt,
  });

  final String id;
  final String userId;
  final String category;
  final String? description;
  final double estimatedWeight;
  final String address;
  final double latitude;
  final double longitude;
  final List<String> imageUrls;
  final SubmissionStatus status;
  final String? assignedCollectorId;
  final DateTime? pickupScheduledAt;
  final DateTime? completedAt;
  final DateTime createdAt;
  final DateTime updatedAt;

  /// The action a collector can take next from this status, or `null` if
  /// none (the submission is not currently actionable by a collector — e.g.
  /// still `PENDING` unassigned, or already past the collector's stage).
  SubmissionAction? get nextAction => switch (status) {
        SubmissionStatus.assigned => SubmissionAction.accept,
        SubmissionStatus.accepted => SubmissionAction.start,
        SubmissionStatus.inProgress => SubmissionAction.complete,
        _ => null,
      };

  factory Submission.fromJson(Map<String, dynamic> json) {
    return Submission(
      id: json['id'] as String,
      userId: json['userId'] as String,
      category: json['category'] as String,
      description: json['description'] as String?,
      estimatedWeight: (json['estimatedWeight'] as num).toDouble(),
      address: json['address'] as String,
      latitude: (json['latitude'] as num).toDouble(),
      longitude: (json['longitude'] as num).toDouble(),
      imageUrls: (json['imageUrls'] as List<dynamic>? ?? const [])
          .map((e) => e as String)
          .toList(growable: false),
      status: SubmissionStatus.fromWire(json['status'] as String),
      assignedCollectorId: json['assignedCollectorId'] as String?,
      pickupScheduledAt: json['pickupScheduledAt'] != null
          ? DateTime.parse(json['pickupScheduledAt'] as String)
          : null,
      completedAt:
          json['completedAt'] != null ? DateTime.parse(json['completedAt'] as String) : null,
      createdAt: DateTime.parse(json['createdAt'] as String),
      updatedAt: DateTime.parse(json['updatedAt'] as String),
    );
  }
}

/// A collector-workflow transition, matching one of the
/// `PATCH /submissions/:id/{accept,start,complete}` endpoints.
enum SubmissionAction {
  accept('accept', 'Accept pickup'),
  start('start', 'Start pickup'),
  complete('complete', 'Mark collected');

  const SubmissionAction(this.path, this.label);

  /// URL segment appended to `/submissions/:id/`.
  final String path;

  /// Button label shown to the collector.
  final String label;
}
