import { z } from 'zod';

/**
 * Request schemas for the auth module. Applied by the validate middleware
 * before controllers run — see docs/engineering/05_API.md (Validation Rules).
 */

const email = z.string().trim().toLowerCase().email('A valid email address is required');

const password = z
  .string()
  .min(8, 'Password must be at least 8 characters')
  .max(128, 'Password must be at most 128 characters');

export const registerSchema = z
  .object({
    email,
    password,
    confirmPassword: z.string(),
    fullName: z.string().trim().min(2, 'Full name must be at least 2 characters').max(100),
    phone: z.string().trim().min(7).max(20).optional(),
    region: z.string().trim().min(2).max(100).optional(),
  })
  .refine((body) => body.password === body.confirmPassword, {
    path: ['confirmPassword'],
    message: 'Passwords do not match',
  });

export const loginSchema = z.object({
  email,
  password: z.string().min(1, 'Password is required'),
});

export const refreshSchema = z.object({
  refreshToken: z.string().min(1, 'Refresh token is required'),
});

export const logoutSchema = refreshSchema;

export type RegisterInput = z.infer<typeof registerSchema>;
export type LoginInput = z.infer<typeof loginSchema>;
export type RefreshInput = z.infer<typeof refreshSchema>;
export type LogoutInput = z.infer<typeof logoutSchema>;
