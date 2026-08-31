import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../auth/providers/auth_providers.dart';
import '../data/submissions_repository.dart';
import '../models/submission.dart';

final submissionsRepositoryProvider = Provider<SubmissionsRepository>((ref) {
  return SubmissionsRepository(apiClient: ref.watch(apiClientProvider));
});

/// The consumer's own submissions (`GET /submissions` — `findByUser`, so
/// this is naturally scoped to "my reports", not a global list).
final submissionsProvider = FutureProvider<List<Submission>>((ref) async {
  final repository = ref.watch(submissionsRepositoryProvider);
  final result = await repository.list();
  return result.when(success: (items) => items, failure: (failure) => throw failure);
});

final submissionDetailProvider = FutureProvider.family<Submission, String>((ref, id) async {
  final repository = ref.watch(submissionsRepositoryProvider);
  final result = await repository.fetchById(id);
  return result.when(success: (s) => s, failure: (failure) => throw failure);
});

/// Drives the "Report Waste" form's submit button.
class CreateSubmissionController extends Notifier<AsyncValue<Submission?>> {
  @override
  AsyncValue<Submission?> build() => const AsyncValue.data(null);

  Future<bool> submit({
    required String category,
    String? description,
    required double estimatedWeight,
    required String address,
    required double latitude,
    required double longitude,
    List<String>? imageUrls,
  }) async {
    state = const AsyncValue.loading();
    final repository = ref.read(submissionsRepositoryProvider);
    final result = await repository.create(
      category: category,
      description: description,
      estimatedWeight: estimatedWeight,
      address: address,
      latitude: latitude,
      longitude: longitude,
      imageUrls: imageUrls,
    );
    return result.when(
      success: (submission) {
        state = AsyncValue.data(submission);
        ref.invalidate(submissionsProvider);
        return true;
      },
      failure: (failure) {
        state = AsyncValue.error(failure, StackTrace.current);
        return false;
      },
    );
  }
}

final createSubmissionControllerProvider =
    NotifierProvider<CreateSubmissionController, AsyncValue<Submission?>>(
  CreateSubmissionController.new,
);

/// Drives cancel (delete-while-PENDING) from the detail screen.
class SubmissionActionController extends Notifier<AsyncValue<void>> {
  @override
  AsyncValue<void> build() => const AsyncValue.data(null);

  Future<bool> cancel(String submissionId) async {
    state = const AsyncValue.loading();
    final repository = ref.read(submissionsRepositoryProvider);
    final result = await repository.delete(submissionId);
    return result.when(
      success: (_) {
        state = const AsyncValue.data(null);
        ref.invalidate(submissionsProvider);
        return true;
      },
      failure: (failure) {
        state = AsyncValue.error(failure, StackTrace.current);
        return false;
      },
    );
  }
}

final submissionActionControllerProvider =
    NotifierProvider<SubmissionActionController, AsyncValue<void>>(
  SubmissionActionController.new,
);
