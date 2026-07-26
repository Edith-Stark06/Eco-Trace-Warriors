import type { Request, Response } from 'express';
import { Prisma } from '@prisma/client';
import { errorHandler } from '@shared/middleware';
import { ConflictError } from '@shared/errors';
import { createLogger } from '@shared/logging';

/** Silent logger so error-path assertions don't spam test output. */
const logger = createLogger({ logLevel: 'fatal', nodeEnv: 'test' });

/** Minimal Response stub capturing the status + JSON body the handler sends. */
function buildRes(): { res: Response; status: jest.Mock; json: jest.Mock } {
  const json = jest.fn();
  const status = jest.fn().mockReturnValue({ json });
  const res = { status, json } as unknown as Response;
  return { res, status, json };
}

const req = { id: 'req-1', path: '/api/v1/thing' } as unknown as Request;

/** Builds a known Prisma error carrying the given code. */
function prismaError(code: string): Prisma.PrismaClientKnownRequestError {
  return new Prisma.PrismaClientKnownRequestError('db failure detail', {
    code,
    clientVersion: 'test',
  });
}

describe('errorHandler — Prisma error mapping', () => {
  it('maps P2002 (unique constraint) to 409 CONFLICT', () => {
    const { res, status, json } = buildRes();

    errorHandler(logger)(prismaError('P2002'), req, res, jest.fn());

    expect(status).toHaveBeenCalledWith(409);
    expect(json).toHaveBeenCalledWith({
      success: false,
      error: { code: 'CONFLICT', message: expect.any(String) },
    });
  });

  it('maps P2025 (record not found) to 404 NOT_FOUND', () => {
    const { res, status, json } = buildRes();

    errorHandler(logger)(prismaError('P2025'), req, res, jest.fn());

    expect(status).toHaveBeenCalledWith(404);
    expect(json).toHaveBeenCalledWith({
      success: false,
      error: { code: 'NOT_FOUND', message: expect.any(String) },
    });
  });

  it('does not leak the raw Prisma message to the client', () => {
    const { res, json } = buildRes();

    errorHandler(logger)(prismaError('P2002'), req, res, jest.fn());

    const body = json.mock.calls[0][0] as { error: { message: string } };
    expect(body.error.message).not.toContain('db failure detail');
  });

  it('keeps unmapped Prisma codes as a generic 500', () => {
    const { res, status, json } = buildRes();

    errorHandler(logger)(prismaError('P2003'), req, res, jest.fn());

    expect(status).toHaveBeenCalledWith(500);
    expect(json).toHaveBeenCalledWith({
      success: false,
      error: { code: 'INTERNAL_ERROR', message: 'An unexpected error occurred.' },
    });
  });
});

describe('errorHandler — precedence and fallback', () => {
  it('honours AppError over the Prisma branch and preserves its status/code', () => {
    const { res, status, json } = buildRes();

    errorHandler(logger)(new ConflictError('Already exists.'), req, res, jest.fn());

    expect(status).toHaveBeenCalledWith(409);
    expect(json).toHaveBeenCalledWith({
      success: false,
      error: { code: 'CONFLICT', message: 'Already exists.' },
    });
  });

  it('maps an unknown (non-Prisma) error to a generic 500', () => {
    const { res, status, json } = buildRes();

    errorHandler(logger)(new Error('boom'), req, res, jest.fn());

    expect(status).toHaveBeenCalledWith(500);
    expect(json).toHaveBeenCalledWith({
      success: false,
      error: { code: 'INTERNAL_ERROR', message: 'An unexpected error occurred.' },
    });
  });
});
