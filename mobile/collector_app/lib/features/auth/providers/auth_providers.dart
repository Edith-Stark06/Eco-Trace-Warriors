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

/// Coarse-grained session state the router/splash screen branches on.
enum AuthStatus { unknown, authenticated, unauthenticated }

class AuthState {
  const AuthState({
    this.status = AuthStatus.unknown,
    this.profile,
    this.isLoading = false,
    this.failure,
  });

  final AuthStatus status;
  final CollectorProfile? profile;
  final bool isLoading;
  final AppFailure? failure;

  AuthState copyWith({
    AuthStatus? status,
    CollectorProfile? profile,
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

/// Owns the collector's session lifecycle: bootstrap (splash), login, logout.
///
/// riverpod 3.x's `Notifier<T>` (not the removed `StateNotifier<T>`):
/// dependencies are read via `ref` inside methods rather than injected
/// through a constructor, and `build()` supplies the initial state.
class AuthController extends Notifier<AuthState> {
  @override
  AuthState build() => const AuthState();

  AuthRepository get _repository => ref.read(authRepositoryProvider);

  /// Called once at app start (splash screen): checks for a stored session
  /// and validates it against `/auth/me` before entering the app.
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
        // Stored token rejected/expired — fall back to the login screen
        // rather than surfacing an error on a screen the collector never
        // interacted with.
        state = state.copyWith(status: AuthStatus.unauthenticated, isLoading: false);
      },
    );
  }

  Future<void> login({required String email, required String password}) async {
    state = state.copyWith(isLoading: true, clearFailure: true);
    final result = await _repository.login(email: email, password: password);
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
