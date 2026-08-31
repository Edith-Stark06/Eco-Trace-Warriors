/// Mirrors `PublicSubmission`
/// (`backend/src/modules/submission/submission.types.ts`) and the
/// `SubmissionStatus` enum (`backend/prisma/schema.prisma`).
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

  String get label => switch (this) {
        SubmissionStatus.pending => 'Awaiting assignment',
        SubmissionStatus.assigned => 'Collector assigned',
        SubmissionStatus.accepted => 'Pickup accepted',
        SubmissionStatus.inProgress => 'Pickup in progress',
        SubmissionStatus.collected => 'Collected',
        SubmissionStatus.recycling => 'Being recycled',
        SubmissionStatus.recycled => 'Recycled',
        SubmissionStatus.completed => 'Completed',
        SubmissionStatus.rejected => 'Rejected',
      };
}

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
    required this.recoveredWeight,
    required this.co2Saved,
    required this.rewardIssued,
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
  final double? recoveredWeight;
  final double? co2Saved;
  final bool rewardIssued;
  final DateTime createdAt;
  final DateTime updatedAt;

  /// A consumer may edit/cancel their own submission only while it has not
  /// yet entered the assignment flow (`submission.service.ts` —
  /// `update()`/`delete()`: "Owners may only edit before the submission
  /// enters the assignment flow").
  bool get isEditable => status == SubmissionStatus.pending;

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
      recoveredWeight:
          json['recoveredWeight'] != null ? (json['recoveredWeight'] as num).toDouble() : null,
      co2Saved: json['co2Saved'] != null ? (json['co2Saved'] as num).toDouble() : null,
      rewardIssued: json['rewardIssued'] as bool? ?? false,
      createdAt: DateTime.parse(json['createdAt'] as String),
      updatedAt: DateTime.parse(json['updatedAt'] as String),
    );
  }
}
