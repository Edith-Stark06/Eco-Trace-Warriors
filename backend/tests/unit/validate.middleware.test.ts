import type { Request, Response } from 'express';
import { z } from 'zod';
import { validate } from '@shared/middleware';
import { ValidationError } from '@shared/errors';

function buildReq(body: unknown = {}, query: unknown = {}): Request {
  return { body, params: {}, query } as Request;
}

describe('validate', () => {
  const res = {} as Response;
  const bodySchema = z.object({ email: z.string().email(), age: z.coerce.number().int() });

  it('replaces the segment with parsed (coerced) data and calls next()', () => {
    const req = buildReq({ email: 'a@b.com', age: '30' });
    const next = jest.fn();

    validate({ body: bodySchema })(req, res, next);

    expect(req.body).toEqual({ email: 'a@b.com', age: 30 });
    expect(next).toHaveBeenCalledWith();
  });

  it('throws ValidationError with field-level details for an invalid body', () => {
    const req = buildReq({ email: 'not-an-email', age: 'NaN' });

    try {
      validate({ body: bodySchema })(req, res, jest.fn());
      throw new Error('expected ValidationError');
    } catch (err) {
      expect(err).toBeInstanceOf(ValidationError);
      const details = (err as ValidationError).details ?? [];
      expect(details.map((d) => d.field)).toEqual(expect.arrayContaining(['email', 'age']));
    }
  });

  it('validates the query segment independently', () => {
    const req = buildReq({}, { page: 'zero' });
    const querySchema = z.object({ page: z.coerce.number().int().min(1) });

    expect(() => validate({ query: querySchema })(req, res, jest.fn())).toThrow(ValidationError);
  });

  it('passes through when no schema matches a segment', () => {
    const next = jest.fn();

    validate({})(buildReq({ anything: true }), res, next);

    expect(next).toHaveBeenCalledWith();
  });
});
