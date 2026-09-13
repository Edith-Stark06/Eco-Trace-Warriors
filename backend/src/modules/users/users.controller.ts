import type { Request, Response } from 'express';
import type { UsersService } from './users.service';
import type { CreateUserRequest, ListUsersQuery } from './users.schemas';
import type { CreateUserResponse, UserListResponse } from './users.types';

export interface UsersController {
  list(req: Request, res: Response): Promise<void>;
  create(req: Request, res: Response): Promise<void>;
}

/** Thin controller: validates input (already parsed by middleware), delegates to service. */
export function createUsersController(usersService: UsersService): UsersController {
  return {
    async list(req: Request, res: Response): Promise<void> {
      const { role } = req.query as unknown as ListUsersQuery;
      const users = await usersService.listByRole(role);
      const body: UserListResponse = { success: true, data: users };
      res.status(200).json(body);
    },

    async create(req: Request, res: Response): Promise<void> {
      const input = req.body as CreateUserRequest;
      const result = await usersService.createUser(input);
      const body: CreateUserResponse = { success: true, data: result };
      res.status(201).json(body);
    },
  };
}
