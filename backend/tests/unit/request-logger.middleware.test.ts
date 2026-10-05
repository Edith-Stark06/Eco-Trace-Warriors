import { Writable } from 'node:stream';
import express from 'express';
import request from 'supertest';
import { createLogger } from '@shared/logging';
import { requestId, requestLogger } from '@shared/middleware';

/** Collects log lines emitted during a request. */
function captureStream(): { stream: Writable; records: () => Record<string, unknown>[] } {
  const chunks: string[] = [];
  const stream = new Writable({
    write(chunk: Buffer, _encoding, callback): void {
      chunks.push(chunk.toString());
      callback();
    },
  });
  const records = (): Record<string, unknown>[] =>
    chunks
      .join('')
      .split('\n')
      .filter((line) => line.length > 0)
      .map((line) => JSON.parse(line) as Record<string, unknown>);
  return { stream, records };
}

/** Minimal app: requestId → requestLogger → a route returning the given status. */
function buildApp(stream: Writable, status: number): express.Express {
  const logger = createLogger({ logLevel: 'info', nodeEnv: 'test' }, stream);
  const app = express();
  app.use(requestId());
  app.use(requestLogger(logger));
  app.get('/thing', (_req, res) => {
    res.status(status).json({ ok: status < 400 });
  });
  return app;
}

describe('requestLogger', () => {
  it('logs response status, duration, and the correlation id on completion', async () => {
    const { stream, records } = captureStream();

    await request(buildApp(stream, 200)).get('/thing').set('X-Request-Id', 'corr-123');

    const completion = records().find((r) => typeof r.durationMs === 'number');
    expect(completion).toBeDefined();
    expect(completion?.status).toBe(200);
    expect(completion?.requestId).toBe('corr-123');
    expect(completion?.durationMs).toEqual(expect.any(Number));
    expect(completion?.durationMs as number).toBeGreaterThanOrEqual(0);
  });

  it('logs 4xx responses at warn level with the status surfaced', async () => {
    const { stream, records } = captureStream();

    await request(buildApp(stream, 404)).get('/thing');

    const completion = records().find((r) => typeof r.durationMs === 'number');
    expect(completion?.status).toBe(404);
    // Pino level 40 === warn.
    expect(completion?.level).toBe(40);
    expect(completion?.requestId).toEqual(expect.any(String));
  });
});
