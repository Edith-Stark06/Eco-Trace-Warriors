import { randomBytes } from 'node:crypto';
import type { UserRole } from '@prisma/client';
import { ConflictError, InternalError } from '@shared/errors';
import type { Logger } from '@shared/logging';
import type { PasswordService, UserRecord, UserRepository } from '@modules/auth';
import type { CreateUserRequest } from './users.schemas';
import type { CreateUserResult, UserListItem } from './users.types';

/** Dependencies injected into the users service. */
export interface UsersServiceDeps {
  readonly users: UserRepository;
  readonly passwords: PasswordService;
  readonly logger: Logger;
}

export interface UsersService {
  /** Active users with the given role, mapped to the lightweight list DTO. */
  listByRole(role: UserRole): Promise<UserListItem[]>;
  /**
   * Admin-provisions an operational account (COLLECTOR/RECYCLER/GOVERNMENT)
   * with a server-generated password. Returns the plaintext password exactly
   * once — it is never persisted or logged.
   */
  createUser(input: CreateUserRequest): Promise<CreateUserResult>;
}

/** Maps a full user record to the lightweight list item (no secrets, no PII beyond contact). */
function toListItem(user: UserRecord): UserListItem {
  return {
    id: user.id,
    fullName: user.fullName,
    email: user.email,
    region: user.region,
    role: user.role.name,
  };
}

/**
 * Character set for generated passwords: excludes visually ambiguous
 * characters (0/O, 1/l/I) and symbols that commonly cause trouble when
 * copy-pasted into shells or URLs (quotes, backslash, backtick, whitespace).
 */
const PASSWORD_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%*-_=';
const PASSWORD_LENGTH = 16;

/**
 * Draws one unbiased character from `alphabet` using rejection sampling over
 * `crypto.randomBytes` — never Math.random(). Rejection sampling avoids the
 * small modulo bias that `byte % alphabet.length` alone would introduce.
 */
function randomAlphabetChar(alphabet: string): string {
  const max = 256 - (256 % alphabet.length);
  let byte: number;
  do {
    byte = randomBytes(1)[0] ?? 0;
  } while (byte >= max);
  return alphabet[byte % alphabet.length] as string;
}

/** Generates a cryptographically secure random password. Never Math.random(). */
function generatePassword(): string {
  return Array.from({ length: PASSWORD_LENGTH }, () => randomAlphabetChar(PASSWORD_ALPHABET)).join(
    '',
  );
}

/** Derives an initial display name from the email local-part (e.g. "john.doe@x.com" → "john.doe"). */
function fullNameFromEmail(email: string): string {
  return email.split('@')[0] ?? email;
}

/**
 * Creates the users service. Reuses the auth module's UserRepository — the user
 * table has a single owner (auth), so we depend on its interface rather than
 * introducing a second Prisma access point (keeps modules decoupled).
 */
export function createUsersService(deps: UsersServiceDeps): UsersService {
  return {
    async listByRole(role: UserRole): Promise<UserListItem[]> {
      const records = await deps.users.findByRole(role);
      return records.map(toListItem);
    },

    async createUser(input: CreateUserRequest): Promise<CreateUserResult> {
      const existing = await deps.users.findByEmail(input.email);
      if (existing) {
        throw new ConflictError('An account with this email already exists.');
      }

      const roleId = await deps.users.findRoleId(input.role);
      if (!roleId) {
        // Roles are seeded by prisma/seed.ts; absence is a deployment fault.
        deps.logger.error({ role: input.role }, 'Required role missing from database');
        throw new InternalError();
      }

      const generatedPassword = generatePassword();
      const passwordHash = await deps.passwords.hash(generatedPassword);

      const user = await deps.users.create({
        fullName: fullNameFromEmail(input.email),
        email: input.email,
        passwordHash,
        roleId,
      });

      // Never log the plaintext password — only identifiers.
      deps.logger.info({ userId: user.id, role: input.role }, 'Admin created user');

      return {
        user: {
          id: user.id,
          email: user.email,
          role: user.role.name,
          createdAt: user.createdAt.toISOString(),
        },
        generatedPassword,
      };
    },
  };
}
