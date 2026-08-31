// Auth domain models, mirroring `backend/src/modules/auth/auth.types.ts`
// field-for-field — the wire contract is not guessed.

/// The authenticated collector's public profile.
/// Mirrors `PublicUser` (`backend/src/modules/auth/auth.types.ts`).
class CollectorProfile {
  const CollectorProfile({
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

  /// One of `ADMIN | GOVERNMENT | RECYCLER | COLLECTOR | CONSUMER`
  /// (`UserRole` enum, `backend/prisma/schema.prisma`).
  final String role;
  final bool emailVerified;
  final DateTime createdAt;

  bool get isCollector => role == 'COLLECTOR';

  factory CollectorProfile.fromJson(Map<String, dynamic> json) {
    return CollectorProfile(
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

/// Access + refresh token pair. Mirrors `AuthTokens`.
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

/// Result of login: profile + a fresh token pair. Mirrors `AuthResult`.
class AuthResult {
  const AuthResult({required this.profile, required this.tokens});

  final CollectorProfile profile;
  final AuthTokens tokens;

  factory AuthResult.fromJson(Map<String, dynamic> json) {
    return AuthResult(
      profile: CollectorProfile.fromJson(json['user'] as Map<String, dynamic>),
      tokens: AuthTokens.fromJson(json),
    );
  }
}
