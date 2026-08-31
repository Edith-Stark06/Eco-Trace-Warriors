import 'package:dio/dio.dart';

import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/utils/result.dart';
import '../models/submission.dart';

/// Talks to `backend/`'s submission module for the consumer-owned surface:
/// `POST /submissions`, `GET /submissions`, `GET /submissions/:id`,
/// `PATCH /submissions/:id`, `DELETE /submissions/:id`
/// (`backend/src/modules/submission/submission.routes.ts`). This is the
/// consumer's "report e-waste for pickup" flow — see
/// `reports/P6_4_MOBILE_CONSUMER.md` for why this, not an AI-detection
/// capture flow, is what the real backend actually models.
class SubmissionsRepository {
  SubmissionsRepository({required ApiClient apiClient}) : _apiClient = apiClient;

  final ApiClient _apiClient;

  Future<Result<Submission>> create({
    required String category,
    String? description,
    required double estimatedWeight,
    required String address,
    required double latitude,
    required double longitude,
    List<String>? imageUrls,
  }) async {
    try {
      final response = await _apiClient.post(
        '/submissions',
        data: {
          'category': category,
          if (description != null && description.isNotEmpty) 'description': description,
          'estimatedWeight': estimatedWeight,
          'address': address,
          'latitude': latitude,
          'longitude': longitude,
          if (imageUrls != null && imageUrls.isNotEmpty) 'imageUrls': imageUrls,
        },
      );
      return Result.success(
        Submission.fromJson((response.data as Map<String, dynamic>)['data'] as Map<String, dynamic>),
      );
    } on DioException catch (e) {
      return Result.failure(mapDioExceptionToFailure(e));
    }
  }

  Future<Result<List<Submission>>> list() async {
    try {
      final response = await _apiClient.get('/submissions');
      final items = ((response.data as Map<String, dynamic>)['data'] as List<dynamic>)
          .map((e) => Submission.fromJson(e as Map<String, dynamic>))
          .toList(growable: false);
      return Result.success(items);
    } on DioException catch (e) {
      return Result.failure(mapDioExceptionToFailure(e));
    }
  }

  Future<Result<Submission>> fetchById(String id) async {
    try {
      final response = await _apiClient.get('/submissions/$id');
      return Result.success(
        Submission.fromJson((response.data as Map<String, dynamic>)['data'] as Map<String, dynamic>),
      );
    } on DioException catch (e) {
      return Result.failure(mapDioExceptionToFailure(e));
    }
  }

  Future<Result<Submission>> update(
    String id, {
    String? category,
    String? description,
    double? estimatedWeight,
    String? address,
    double? latitude,
    double? longitude,
  }) async {
    try {
      final response = await _apiClient.patch(
        '/submissions/$id',
        data: {
          if (category != null) 'category': category,
          if (description != null) 'description': description,
          if (estimatedWeight != null) 'estimatedWeight': estimatedWeight,
          if (address != null) 'address': address,
          if (latitude != null) 'latitude': latitude,
          if (longitude != null) 'longitude': longitude,
        },
      );
      return Result.success(
        Submission.fromJson((response.data as Map<String, dynamic>)['data'] as Map<String, dynamic>),
      );
    } on DioException catch (e) {
      return Result.failure(mapDioExceptionToFailure(e));
    }
  }

  Future<Result<void>> delete(String id) async {
    try {
      await _apiClient.delete('/submissions/$id');
      return const Result.success(null);
    } on DioException catch (e) {
      return Result.failure(mapDioExceptionToFailure(e));
    }
  }
}
