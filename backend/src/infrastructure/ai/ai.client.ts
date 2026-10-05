/**
 * AI service client provider — Phase 8 (Artificial Intelligence).
 *
 * Thin typed HTTP client for the internal AI API
 * (docs/engineering/05_API.md — Internal AI Service API). AI calls are
 * advisory: consumers must degrade gracefully when the service is unavailable
 * (docs/engineering/08_AI.md — Degradation & Fallbacks).
 */
export interface AiClient {
  /** Classifies a device image; resolves null when the AI service is unavailable. */
  classifyDevice(imageUrl: string): Promise<DeviceClassification | null>;
}

export interface DeviceClassification {
  readonly category: string;
  readonly condition: string;
  readonly confidence: number;
  readonly modelVersion: string;
}

/** Placeholder until Phase 8: behaves as "service unavailable" (graceful degradation). */
export function createAiClient(): AiClient {
  return {
    classifyDevice: () => Promise.resolve(null),
  };
}
