import { z } from 'zod';

/**
 * Client-side login validation (UX only — the server re-validates and is the
 * authority). Kept minimal: a well-formed email and a non-empty password.
 * Password strength rules belong to registration, not login.
 */
export const loginSchema = z.object({
  email: z.string().trim().min(1, 'Email is required').email('Enter a valid email address'),
  password: z.string().min(1, 'Password is required'),
});

export type LoginFormValues = z.infer<typeof loginSchema>;
