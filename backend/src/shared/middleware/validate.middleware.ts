import type { RequestHandler } from 'express';
import type { ZodType } from 'zod';
import { ValidationError } from '@shared/errors';
import type { ErrorDetail } from '@shared/errors';

/** Zod schemas to apply to each request segment. All optional. */
export interface ValidationSchemas {
  readonly body?: ZodType<unknown>;
  readonly params?: ZodType<unknown>;
  readonly query?: ZodType<unknown>;
}

/**
 * Validates request segments against Zod schemas before the controller runs.
 * Failures throw ValidationError (→ 400) with field-level details per the
 * error contract in docs/engineering/05_API.md. Parsed (coerced, stripped)
 * values replace the raw segment so controllers only ever see typed input.
 */
export function validate(schemas: ValidationSchemas): RequestHandler {
  return (req, _res, next): void => {
    const details: ErrorDetail[] = [];

    for (const segment of ['body', 'params', 'query'] as const) {
      const schema = schemas[segment];
      if (!schema) continue;

      const result = schema.safeParse(req[segment]);
      if (result.success) {
        req[segment] = result.data;
      } else {
        for (const issue of result.error.issues) {
          details.push({
            field: issue.path.length > 0 ? issue.path.join('.') : segment,
            issue: issue.message,
          });
        }
      }
    }

    if (details.length > 0) {
      throw new ValidationError('Request validation failed.', details);
    }
    next();
  };
}
