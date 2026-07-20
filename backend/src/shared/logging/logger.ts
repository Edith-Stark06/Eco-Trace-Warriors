import { pino } from 'pino';
import type { DestinationStream, Logger } from 'pino';
import type { AppConfig } from '@shared/config';

/** Keys that must never appear in log output. */
const REDACTED_PATHS = [
  'req.headers.authorization',
  'req.headers.cookie',
  'password',
  'token',
  'secret',
];

/**
 * Creates the application logger.
 * Structured JSON in production/test; pretty-printed in development.
 * An explicit destination stream may be injected (used by tests).
 */
export function createLogger(
  config: Pick<AppConfig, 'logLevel' | 'nodeEnv'>,
  destination?: DestinationStream,
): Logger {
  const options = {
    level: config.logLevel,
    redact: { paths: REDACTED_PATHS, censor: '[REDACTED]' },
    base: { service: 'ecotrace-backend' },
    timestamp: pino.stdTimeFunctions.isoTime,
    transport:
      config.nodeEnv === 'development' && !destination
        ? { target: 'pino-pretty', options: { colorize: true, singleLine: true } }
        : undefined,
  };

  return destination ? pino(options, destination) : pino(options);
}

export type { Logger, DestinationStream };
