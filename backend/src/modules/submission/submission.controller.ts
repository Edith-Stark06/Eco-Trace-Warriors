import type { Request, Response } from 'express';
import { getAuthContext } from '@modules/auth';
import type {
  AssignCollectorInput,
  AssignRecyclerInput,
  CompleteRecyclingInput,
  CreateSubmissionInput,
  UpdateSubmissionInput,
} from './submission.schemas';
import type { SubmissionActor, SubmissionService } from './submission.service';
import type {
  CompleteRecyclingWithRewardResponse,
  SubmissionListResponse,
  SubmissionResponse,
} from './submission.types';

export interface SubmissionController {
  create(req: Request, res: Response): Promise<void>;
  list(req: Request, res: Response): Promise<void>;
  getById(req: Request, res: Response): Promise<void>;
  update(req: Request, res: Response): Promise<void>;
  delete(req: Request, res: Response): Promise<void>;
  // Collector workflow (Phase 6)
  assignCollector(req: Request, res: Response): Promise<void>;
  acceptAssignment(req: Request, res: Response): Promise<void>;
  startPickup(req: Request, res: Response): Promise<void>;
  completePickup(req: Request, res: Response): Promise<void>;
  collectorDashboard(req: Request, res: Response): Promise<void>;
  // Recycler workflow (Phase 7)
  assignRecycler(req: Request, res: Response): Promise<void>;
  startRecycling(req: Request, res: Response): Promise<void>;
  completeRecycling(req: Request, res: Response): Promise<void>;
  recyclerDashboard(req: Request, res: Response): Promise<void>;
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

    async assignCollector(req: Request, res: Response): Promise<void> {
      const { id } = req.params as { id: string };
      const { collectorId } = req.body as AssignCollectorInput;
      const result = await service.assignCollector(actorOf(req), id, collectorId);
      const body: SubmissionResponse = { success: true, data: result };
      res.status(200).json(body);
    },

    async acceptAssignment(req: Request, res: Response): Promise<void> {
      const { id } = req.params as { id: string };
      const result = await service.acceptAssignment(actorOf(req), id);
      const body: SubmissionResponse = { success: true, data: result };
      res.status(200).json(body);
    },

    async startPickup(req: Request, res: Response): Promise<void> {
      const { id } = req.params as { id: string };
      const result = await service.startPickup(actorOf(req), id);
      const body: SubmissionResponse = { success: true, data: result };
      res.status(200).json(body);
    },

    async completePickup(req: Request, res: Response): Promise<void> {
      const { id } = req.params as { id: string };
      const result = await service.completePickup(actorOf(req), id);
      const body: SubmissionResponse = { success: true, data: result };
      res.status(200).json(body);
    },

    async collectorDashboard(req: Request, res: Response): Promise<void> {
      const result = await service.getCollectorDashboard(actorOf(req));
      const body: SubmissionListResponse = { success: true, data: result };
      res.status(200).json(body);
    },

    async assignRecycler(req: Request, res: Response): Promise<void> {
      const { id } = req.params as { id: string };
      const { recyclerId } = req.body as AssignRecyclerInput;
      const result = await service.assignRecycler(actorOf(req), id, recyclerId);
      const body: SubmissionResponse = { success: true, data: result };
      res.status(200).json(body);
    },

    async startRecycling(req: Request, res: Response): Promise<void> {
      const { id } = req.params as { id: string };
      const result = await service.startRecycling(actorOf(req), id);
      const body: SubmissionResponse = { success: true, data: result };
      res.status(200).json(body);
    },

    async completeRecycling(req: Request, res: Response): Promise<void> {
      const { id } = req.params as { id: string };
      const result = await service.completeRecycling(
        actorOf(req),
        id,
        req.body as CompleteRecyclingInput,
      );
      const body: CompleteRecyclingWithRewardResponse = { success: true, data: result };
      res.status(200).json(body);
    },

    async recyclerDashboard(req: Request, res: Response): Promise<void> {
      const result = await service.getRecyclerDashboard(actorOf(req));
      const body: SubmissionListResponse = { success: true, data: result };
      res.status(200).json(body);
    },
  };
}
