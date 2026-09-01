import 'package:dio/dio.dart';
import 'package:ecotrace_consumer/core/network/api_client.dart';
import 'package:ecotrace_consumer/core/storage/secure_storage_service.dart';
import 'package:ecotrace_consumer/features/auth/data/auth_repository.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockApiClient extends Mock implements ApiClient {}

class _MockSecureStorageService extends Mock implements SecureStorageService {}

void main() {
  late _MockApiClient apiClient;
  late _MockSecureStorageService secureStorage;
  late AuthRepository repository;

  setUp(() {
    apiClient = _MockApiClient();
    secureStorage = _MockSecureStorageService();
    repository = AuthRepository(apiClient: apiClient, secureStorage: secureStorage);

    when(() => secureStorage.saveAuthToken(any())).thenAnswer((_) async {});
    when(() => secureStorage.saveRefreshToken(any())).thenAnswer((_) async {});
    when(() => secureStorage.saveUserId(any())).thenAnswer((_) async {});
  });

  Response<Map<String, dynamic>> loginResponse(String role) {
    return Response(
      requestOptions: RequestOptions(path: '/auth/login'),
      statusCode: 200,
      data: {
        'success': true,
        'data': {
          'user': {
            'id': 'user-1',
            'fullName': 'Jane Doe',
            'email': 'jane@example.com',
            'phone': null,
            'region': null,
            'role': role,
            'emailVerified': true,
            'createdAt': '2026-01-01T00:00:00.000Z',
          },
          'accessToken': 'access-token',
          'refreshToken': 'refresh-token',
        },
      },
    );
  }

  group('AuthRepository.login', () {
    test('persists tokens and succeeds for a CONSUMER account', () async {
      when(() => apiClient.post('/auth/login', data: any(named: 'data')))
          .thenAnswer((_) async => loginResponse('CONSUMER'));

      final result = await repository.login(email: 'jane@example.com', password: 'secret123');

      expect(result.isSuccess, isTrue);
      verify(() => secureStorage.saveAuthToken('access-token')).called(1);
      verify(() => secureStorage.saveRefreshToken('refresh-token')).called(1);
      verify(() => secureStorage.saveUserId('user-1')).called(1);
    });

    test(
      'rejects a non-CONSUMER account client-side and never persists its tokens (P8.4)',
      () async {
        when(() => apiClient.post('/auth/login', data: any(named: 'data')))
            .thenAnswer((_) async => loginResponse('COLLECTOR'));

        final result = await repository.login(email: 'jane@example.com', password: 'secret123');

        expect(result.isSuccess, isFalse);
        result.when(
          success: (_) => fail('expected a failure result'),
          failure: (failure) {
            expect(failure.message, contains('COLLECTOR'));
            expect(failure.message, contains('not CONSUMER'));
          },
        );
        verifyNever(() => secureStorage.saveAuthToken(any()));
        verifyNever(() => secureStorage.saveRefreshToken(any()));
        verifyNever(() => secureStorage.saveUserId(any()));
      },
    );

    for (final role in ['ADMIN', 'GOVERNMENT', 'RECYCLER']) {
      test('also rejects $role accounts', () async {
        when(() => apiClient.post('/auth/login', data: any(named: 'data')))
            .thenAnswer((_) async => loginResponse(role));

        final result = await repository.login(email: 'jane@example.com', password: 'secret123');

        expect(result.isSuccess, isFalse);
      });
    }
  });
}
