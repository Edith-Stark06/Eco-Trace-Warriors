import bcrypt from 'bcryptjs';

/** Dependencies injected into the password service. */
export interface PasswordServiceDeps {
  /** bcrypt cost factor (from validated config). */
  readonly rounds: number;
}

export interface PasswordService {
  /** Hashes a plaintext password with a per-password salt. */
  hash(plain: string): Promise<string>;
  /** Constant-time comparison of a plaintext password against a stored hash. */
  verify(plain: string, hash: string): Promise<boolean>;
}

/** Creates the password service. Framework-agnostic and fully unit-testable. */
export function createPasswordService(deps: PasswordServiceDeps): PasswordService {
  return {
    async hash(plain: string): Promise<string> {
      return bcrypt.hash(plain, deps.rounds);
    },

    async verify(plain: string, hash: string): Promise<boolean> {
      return bcrypt.compare(plain, hash);
    },
  };
}
