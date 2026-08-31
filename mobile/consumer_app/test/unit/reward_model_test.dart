import 'package:ecotrace_consumer/features/rewards/models/reward.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('RewardBalance.fromJson', () {
    test('parses every field, including int/double distinctions', () {
      final balance = RewardBalance.fromJson({
        'greenCoins': 120,
        'totalRewards': 4,
        'totalCO2Saved': 12.5,
        'totalEnergySaved': 30.25,
        'totalLandfillDiverted': 8.0,
      });

      expect(balance.greenCoins, 120);
      expect(balance.totalRewards, 4);
      expect(balance.totalCO2Saved, 12.5);
      expect(balance.totalEnergySaved, 30.25);
      expect(balance.totalLandfillDiverted, 8.0);
    });
  });

  group('RewardTransaction.fromJson', () {
    test('parses the nested submission fields', () {
      final transaction = RewardTransaction.fromJson({
        'id': 'rt-1',
        'submissionId': 'sub-1',
        'points': 50,
        'reason': 'RECYCLING',
        'createdAt': '2026-01-01T00:00:00.000Z',
        'submission': {
          'id': 'sub-1',
          'category': 'Laptop',
          'status': 'RECYCLED',
          'estimatedWeight': 2.5,
          'createdAt': '2025-12-20T00:00:00.000Z',
        },
      });

      expect(transaction.id, 'rt-1');
      expect(transaction.points, 50);
      expect(transaction.reason, 'RECYCLING');
      expect(transaction.submissionCategory, 'Laptop');
      expect(transaction.submissionStatus, 'RECYCLED');
    });
  });
}
