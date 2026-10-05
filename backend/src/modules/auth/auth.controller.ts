import type { Request, Response } from 'express';
import type { LoginInput, LogoutInput, RefreshInput, RegisterInput } from './auth.schemas';
import type { AuthService } from './auth.service';
import type { AuthResponse, LogoutResponse, MeResponse, TokensResponse } from './auth.types';
import { getAuthContext } from './auth.types';

export interface AuthController {
  register(req: Request, res: Response): Promise<void>;
  login(req: Request, res: Response): Promise<void>;
  refresh(req: Request, res: Response): Promise<void>;
  logout(req: Request, res: Response): Promise<void>;
  getMe(req: Request, res: Response): Promise<void>;
}

/** Thin controller: delegates to the service and shapes the HTTP response. */
export function createAuthController(authService: AuthService): AuthController {
  return {
    async register(req: Request, res: Response): Promise<void> {
      // Body is validated and typed by the validate middleware.
      const result = await authService.register(req.body as RegisterInput);
      const body: AuthResponse = { success: true, data: result };
      res.status(201).json(body);
    },

    async login(req: Request, res: Response): Promise<void> {
      const result = await authService.login(req.body as LoginInput);
      const body: AuthResponse = { success: true, data: result };
      res.status(200).json(body);
    },

    async refresh(req: Request, res: Response): Promise<void> {
      const { refreshToken } = req.body as RefreshInput;
      const tokens = await authService.refresh(refreshToken);
      const body: TokensResponse = { success: true, data: tokens };
      res.status(200).json(body);
    },

    async logout(req: Request, res: Response): Promise<void> {
      const { refreshToken } = req.body as LogoutInput;
      await authService.logout(refreshToken);
      const body: LogoutResponse = { success: true, data: { loggedOut: true } };
      res.status(200).json(body);
    },

    async getMe(req: Request, res: Response): Promise<void> {
      const { userId } = getAuthContext(req);
      const user = await authService.getMe(userId);
      const body: MeResponse = { success: true, data: user };
      res.status(200).json(body);
    },
  };
}
