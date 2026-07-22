import type { Request, Response } from 'express';
import { getAuthContext } from '@modules/auth';
import type { CreateSubmissionInput, UpdateSubmissionInput } from './submission.schemas';
import type { SubmissionActor, SubmissionService } from './submission.service';
import type { SubmissionListResponse, SubmissionResponse } from './submission.types';

export interface SubmissionController {
  create(req: Request, res: Response): Promise<void>;
  list(req: Request, res: Response): Promise<void>;
  getById(req: Request, res: Response): Promise<void>;
  update(req: Request, res: Response): Promise<void>;
  delete(req: Request, res: Response): Promise<void>;
}

/** Reads the authenticated principal as the submission actor. */
function actorOf(req: Request): SubmissionActor {
  const { userId, role } = getAuthContext(req);
  return { userId, role };
}

/** Thin controller: delegates to the service and shapes the HTTP response. */
export function createSubmissionController(service: SubmissionService): SubmissionController {
  return {
    async create(req: Request, res: Response): Promise<void> {
      // Body is validated and typed by the validate middleware.
      const result = await service.create(actorOf(req), req.body as CreateSubmissionInput);
      const body: SubmissionResponse = { success: true, data: result };
      res.status(201).json(body);
    },

    async list(req: Request, res: Response): Promise<void> {
      const result = await service.list(actorOf(req));
      const body: SubmissionListResponse = { success: true, data: result };
      res.status(200).json(body);
    },

    async getById(req: Request, res: Response): Promise<void> {
      const { id } = req.params as { id: string };
      const result = await service.getById(actorOf(req), id);
      const body: SubmissionResponse = { success: true, data: result };
      res.status(200).json(body);
    },

    async update(req: Request, res: Response): Promise<void> {
      const { id } = req.params as { id: string };
      const result = await service.update(actorOf(req), id, req.body as UpdateSubmissionInput);
      const body: SubmissionResponse = { success: true, data: result };
      res.status(200).json(body);
    },

    async delete(req: Request, res: Response): Promise<void> {
      const { id } = req.params as { id: string };
      await service.delete(actorOf(req), id);
      res.status(204).send();
    },
  };
}
