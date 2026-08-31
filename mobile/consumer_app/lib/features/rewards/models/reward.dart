/// Mirrors `RewardBalance` (`backend/src/modules/rewards/reward.service.ts`).
class RewardBalance {
  const RewardBalance({
    required this.greenCoins,
    required this.totalRewards,
    required this.totalCO2Saved,
    required this.totalEnergySaved,
    required this.totalLandfillDiverted,
  });

  final int greenCoins;
  final int totalRewards;
  final double totalCO2Saved;
  final double totalEnergySaved;
  final double totalLandfillDiverted;

  factory RewardBalance.fromJson(Map<String, dynamic> json) {
    return RewardBalance(
      greenCoins: json['greenCoins'] as int,
      totalRewards: json['totalRewards'] as int,
      totalCO2Saved: (json['totalCO2Saved'] as num).toDouble(),
      totalEnergySaved: (json['totalEnergySaved'] as num).toDouble(),
      totalLandfillDiverted: (json['totalLandfillDiverted'] as num).toDouble(),
    );
  }
}

/// Mirrors `RewardTransactionWithSubmission`
/// (`backend/src/modules/rewards/reward.repository.ts`).
class RewardTransaction {
  const RewardTransaction({
    required this.id,
    required this.submissionId,
    required this.points,
    required this.reason,
    required this.createdAt,
    required this.submissionCategory,
    required this.submissionStatus,
  });

  final String id;
  final String submissionId;
  final int points;

  /// One of `RECYCLING | BONUS | CAMPAIGN | ADJUSTMENT | REDEMPTION`
  /// (`RewardReason` enum, `backend/prisma/schema.prisma`).
  final String reason;
  final DateTime createdAt;
  final String submissionCategory;
  final String submissionStatus;

  factory RewardTransaction.fromJson(Map<String, dynamic> json) {
    final submission = json['submission'] as Map<String, dynamic>;
    return RewardTransaction(
      id: json['id'] as String,
      submissionId: json['submissionId'] as String,
      points: json['points'] as int,
      reason: json['reason'] as String,
      createdAt: DateTime.parse(json['createdAt'] as String),
      submissionCategory: submission['category'] as String,
      submissionStatus: submission['status'] as String,
    );
  }
}
