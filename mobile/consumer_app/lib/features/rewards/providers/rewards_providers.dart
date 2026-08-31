import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../auth/providers/auth_providers.dart';
import '../data/rewards_repository.dart';
import '../models/reward.dart';

final rewardsRepositoryProvider = Provider<RewardsRepository>((ref) {
  return RewardsRepository(apiClient: ref.watch(apiClientProvider));
});

final rewardBalanceProvider = FutureProvider<RewardBalance>((ref) async {
  final repository = ref.watch(rewardsRepositoryProvider);
  final result = await repository.fetchBalance();
  return result.when(success: (b) => b, failure: (failure) => throw failure);
});

final rewardHistoryProvider = FutureProvider<List<RewardTransaction>>((ref) async {
  final repository = ref.watch(rewardsRepositoryProvider);
  final result = await repository.fetchHistory();
  return result.when(success: (h) => h, failure: (failure) => throw failure);
});
