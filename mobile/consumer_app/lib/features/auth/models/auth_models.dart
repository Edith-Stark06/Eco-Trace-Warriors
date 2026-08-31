// Auth domain models, mirroring `backend/src/modules/auth/auth.types.ts`
// field-for-field.

/// The authenticated consumer's public profile. Mirrors `PublicUser`.
/// Note: `greenCoins` is **not** part of this shape (`toPublicUser()` in
/// `auth.service.ts` omits it) — the reward balance is fetched separately
/// via `GET /rewards/balance` (`features/rewards`).
class ConsumerProfile {
  const ConsumerProfile({
    required this.id,
    required this.fullName,
    required this.email,
    required this.phone,
    required this.region,
    required this.role,
    required this.emailVerified,
    required this.createdAt,
  });

  final String id;
  final String fullName;
  final String email;
  final String? phone;
  final String? region;

  /// One of `ADMIN | GOVERNMENT | RECYCLER | COLLECTOR | CONSUMER`.
  final String role;
  final bool emailVerified;
  final DateTime createdAt;

  factory ConsumerProfile.fromJson(Map<String, dynamic> json) {
    return ConsumerProfile(
      id: json['id'] as String,
      fullName: json['fullName'] as String,
      email: json['email'] as String,
      phone: json['phone'] as String?,
      region: json['region'] as String?,
      role: json['role'] as String,
      emailVerified: json['emailVerified'] as bool,
      createdAt: DateTime.parse(json['createdAt'] as String),
    );
  }
}

class AuthTokens {
  const AuthTokens({required this.accessToken, required this.refreshToken});

  final String accessToken;
  final String refreshToken;

  factory AuthTokens.fromJson(Map<String, dynamic> json) {
    return AuthTokens(
      accessToken: json['accessToken'] as String,
      refreshToken: json['refreshToken'] as String,
    );
  }
}

class AuthResult {
  const AuthResult({required this.profile, required this.tokens});

  final ConsumerProfile profile;
  final AuthTokens tokens;

  factory AuthResult.fromJson(Map<String, dynamic> json) {
    return AuthResult(
      profile: ConsumerProfile.fromJson(json['user'] as Map<String, dynamic>),
      tokens: AuthTokens.fromJson(json),
    );
  }
}
