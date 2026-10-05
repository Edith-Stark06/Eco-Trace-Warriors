/** Mirrors intelligence/device_ai/api/device_schemas.py PassportVerificationPayload. */
export interface PassportVerification {
  device_id: string;
  verification_status: 'VERIFIED' | 'WARNING' | 'INVALID';
  passport_fingerprint: string;
  checks: Record<string, string>;
  warnings: string[];
  errors: string[];
  verified_at: string;
}

export interface DevicePassportVerificationResponse {
  success: boolean;
  verification: PassportVerification;
}
