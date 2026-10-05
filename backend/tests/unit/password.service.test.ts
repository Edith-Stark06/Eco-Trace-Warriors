import { createPasswordService } from '@modules/auth';

// Low cost factor keeps the suite fast; production rounds come from config.
const service = createPasswordService({ rounds: 4 });

describe('createPasswordService', () => {
  it('produces a bcrypt hash that differs from the plaintext', async () => {
    const hash = await service.hash('correct horse battery staple');

    expect(hash).not.toBe('correct horse battery staple');
    expect(hash).toMatch(/^\$2[aby]\$/);
  });

  it('produces distinct hashes for the same input (per-password salt)', async () => {
    const first = await service.hash('same-password');
    const second = await service.hash('same-password');

    expect(first).not.toBe(second);
  });

  it('verifies a correct password against its hash', async () => {
    const hash = await service.hash('s3cure-password');

    await expect(service.verify('s3cure-password', hash)).resolves.toBe(true);
  });

  it('rejects an incorrect password', async () => {
    const hash = await service.hash('s3cure-password');

    await expect(service.verify('wrong-password', hash)).resolves.toBe(false);
  });
});
