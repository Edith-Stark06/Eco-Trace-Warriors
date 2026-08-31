import 'package:dio/dio.dart';

import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/utils/result.dart';
import '../models/reward.dart';

/// Talks to `backend/`'s rewards module: `GET /rewards/balance`,
/// `GET /rewards/history` (`backend/src/modules/rewards/reward.routes.ts`).
///
/// `POST /rewards/issue/:submissionId` is deliberately not called from this
/// app — it is ADMIN-only (a manual override; rewards are issued
/// automatically when a recycler completes processing, per that route's own
/// comment), so there is no consumer-facing "redeem/issue" action to wire up.
/// The "reward redemption UI" in the design brief is therefore a read-only
/// balance/history view, not a functional redemption flow — no backend
/// endpoint exists for a consumer to redeem points for anything (no
/// catalogue, no `RewardReason.REDEMPTION`-producing consumer route).
class RewardsRepository {
  RewardsRepository({required ApiClient apiClient}) : _apiClient = apiClient;

  final ApiClient _apiClient;

  Future<Result<RewardBalance>> fetchBalance() async {
    try {
      final response = await _apiClient.get('/rewards/balance');
      return Result.success(
        RewardBalance.fromJson((response.data as Map<String, dynamic>)['data'] as Map<String, dynamic>),
      );
    } on DioException catch (e) {
      return Result.failure(mapDioExceptionToFailure(e));
    }
  }

  Future<Result<List<RewardTransaction>>> fetchHistory() async {
    try {
      final response = await _apiClient.get('/rewards/history');
      final items = ((response.data as Map<String, dynamic>)['data'] as List<dynamic>)
          .map((e) => RewardTransaction.fromJson(e as Map<String, dynamic>))
          .toList(growable: false);
      return Result.success(items);
    } on DioException catch (e) {
      return Result.failure(mapDioExceptionToFailure(e));
    }
  }
}
