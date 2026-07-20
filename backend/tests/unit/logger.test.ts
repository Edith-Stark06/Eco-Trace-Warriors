import { Writable } from 'node:stream';
import { createLogger } from '@shared/logging';

/** Collects log lines written by the logger under test. */
function captureStream(): { stream: Writable; lines: () => string } {
  const chunks: string[] = [];
  const stream = new Writable({
    write(chunk: Buffer, _encoding, callback): void {
      chunks.push(chunk.toString());
      callback();
    },
  });
  return { stream, lines: () => chunks.join('') };
}

describe('createLogger', () => {
  it('creates a logger honoring the configured level', () => {
    const logger = createLogger({ logLevel: 'warn', nodeEnv: 'test' });

    expect(logger.level).toBe('warn');
    expect(logger.isLevelEnabled('warn')).toBe(true);
    expect(logger.isLevelEnabled('info')).toBe(false);
  });

  it('suppresses logs below the configured level', () => {
    const { stream, lines } = captureStream();
    const logger = createLogger({ logLevel: 'error', nodeEnv: 'test' }, stream);

    logger.info('should not appear');
    logger.error('should appear');

    expect(lines()).not.toContain('should not appear');
    expect(lines()).toContain('should appear');
  });

  it('emits structured JSON with the service name and ISO timestamp', () => {
    const { stream, lines } = captureStream();
    const logger = createLogger({ logLevel: 'info', nodeEnv: 'test' }, stream);

    logger.info({ module: 'health' }, 'hello');

    const record = JSON.parse(lines()) as Record<string, unknown>;
    expect(record.service).toBe('ecotrace-backend');
    expect(record.msg).toBe('hello');
    expect(record.module).toBe('health');
    expect(Number.isNaN(Date.parse(String(record.time)))).toBe(false);
  });

  it('redacts sensitive keys in log output', () => {
    const { stream, lines } = captureStream();
    const logger = createLogger({ logLevel: 'info', nodeEnv: 'test' }, stream);

    logger.info({ password: 'hunter2', token: 'abc123' }, 'sensitive log');

    expect(lines()).not.toContain('hunter2');
    expect(lines()).not.toContain('abc123');
    expect(lines()).toContain('[REDACTED]');
  });

  it('supports child loggers with bound context', () => {
    const { stream, lines } = captureStream();
    const logger = createLogger({ logLevel: 'info', nodeEnv: 'test' }, stream);

    logger.child({ module: 'health' }).info('from child');

    const record = JSON.parse(lines()) as Record<string, unknown>;
    expect(record.module).toBe('health');
    expect(record.msg).toBe('from child');
  });
});
