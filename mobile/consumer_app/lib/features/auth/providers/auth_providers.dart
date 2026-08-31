import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client.dart';
import '../../../core/storage/secure_storage_service.dart';
import '../../../core/utils/result.dart';
import '../data/auth_repository.dart';
import '../models/auth_models.dart';

final secureStorageServiceProvider = Provider<SecureStorageService>((ref) {
  return SecureStorageService();
});

final apiClientProvider = Provider<ApiClient>((ref) {
  return ApiClient(secureStorage: ref.watch(secureStorageServiceProvider));
});

final authRepositoryProvider = Provider<AuthRepository>((ref) {
  return AuthRepository(
    apiClient: ref.watch(apiClientProvider),
    secureStorage: ref.watch(secureStorageServiceProvider),
  );
});

enum AuthStatus { unknown, authenticated, unauthenticated }

class AuthState {
  const AuthState({
    this.status = AuthStatus.unknown,
    this.profile,
    this.isLoading = false,
    this.failure,
  });

  final AuthStatus status;
  final ConsumerProfile? profile;
  final bool isLoading;
  final AppFailure? failure;

  AuthState copyWith({
    AuthStatus? status,
    ConsumerProfile? profile,
    bool? isLoading,
    AppFailure? failure,
    bool clearFailure = false,
  }) {
    return AuthState(
      status: status ?? this.status,
      profile: profile ?? this.profile,
      isLoading: isLoading ?? this.isLoading,
      failure: clearFailure ? null : (failure ?? this.failure),
    );
  }
}

/// riverpod 3.x `Notifier<T>` (not `StateNotifier` — removed in
/// `flutter_riverpod` 3.4.2; see `reports/P6_3_MOBILE_COLLECTOR.md` §8).
class AuthController extends Notifier<AuthState> {
  @override
  AuthState build() => const AuthState();

  AuthRepository get _repository => ref.read(authRepositoryProvider);

  Future<void> bootstrap() async {
    state = state.copyWith(isLoading: true, clearFailure: true);
    final hasSession = await _repository.hasStoredSession();
    if (!hasSession) {
      state = state.copyWith(status: AuthStatus.unauthenticated, isLoading: false);
      return;
    }
    final result = await _repository.fetchProfile();
    result.when(
      success: (profile) {
        state = state.copyWith(
          status: AuthStatus.authenticated,
          profile: profile,
          isLoading: false,
        );
      },
      failure: (_) {
        state = state.copyWith(status: AuthStatus.unauthenticated, isLoading: false);
      },
    );
  }

  Future<void> login({required String email, required String password}) async {
    state = state.copyWith(isLoading: true, clearFailure: true);
    final result = await _repository.login(email: email, password: password);
    _applyAuthResult(result);
  }

  Future<void> register({
    required String email,
    required String password,
    required String confirmPassword,
    required String fullName,
    String? phone,
    String? region,
  }) async {
    state = state.copyWith(isLoading: true, clearFailure: true);
    final result = await _repository.register(
      email: email,
      password: password,
      confirmPassword: confirmPassword,
      fullName: fullName,
      phone: phone,
      region: region,
    );
    _applyAuthResult(result);
  }

  void _applyAuthResult(Result<ConsumerProfile> result) {
    result.when(
      success: (profile) {
        state = state.copyWith(
          status: AuthStatus.authenticated,
          profile: profile,
          isLoading: false,
        );
      },
      failure: (failure) {
        state = state.copyWith(isLoading: false, failure: failure);
      },
    );
  }

  Future<void> logout() async {
    state = state.copyWith(isLoading: true);
    await _repository.logout();
    state = const AuthState(status: AuthStatus.unauthenticated);
  }

  void clearError() {
    state = state.copyWith(clearFailure: true);
  }
}

final authControllerProvider = NotifierProvider<AuthController, AuthState>(AuthController.new);
