import { createApiInfoService, API_NAME } from '@modules/api-info';
import type { ApiInfoService, ApiInfoServiceDeps } from '@modules/api-info';

function buildService(overrides: Partial<ApiInfoServiceDeps> = {}): ApiInfoService {
  return createApiInfoService({
    name: API_NAME,
    version: 'v1',
    environment: 'test',
    documentationPath: '/api/v1/docs',
    ...overrides,
  });
}

describe('createApiInfoService', () => {
  it('returns the documented envelope from the injected dependencies', () => {
    const service = buildService({
      name: 'Custom API',
      version: 'v2',
      environment: 'production',
      documentationPath: '/api/v2/docs',
    });

    expect(service.getInfo()).toEqual({
      success: true,
      data: {
        name: 'Custom API',
        version: 'v2',
        environment: 'production',
        documentation: '/api/v2/docs',
      },
    });
  });

  it('exposes the product-facing API name constant', () => {
    expect(buildService().getInfo().data.name).toBe(API_NAME);
  });
});
