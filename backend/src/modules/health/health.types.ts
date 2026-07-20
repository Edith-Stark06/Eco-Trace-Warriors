/** Health status payload returned by GET /api/v1/health. */
export interface HealthStatus {
  success: true;
  message: string;
  version: string;
  timestamp: string;
  uptime: number;
}
