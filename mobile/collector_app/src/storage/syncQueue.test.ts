import AsyncStorage from '@react-native-async-storage/async-storage';
import { syncQueueStorage } from './syncQueue';

describe('syncQueueStorage', () => {
  beforeEach(async () => {
    await AsyncStorage.clear();
  });

  it('starts empty', async () => {
    expect(await syncQueueStorage.getAll()).toEqual([]);
  });

  it('enqueues a device confirmation with pending status', async () => {
    const item = await syncQueueStorage.enqueue('dev-001', 'laptop');
    expect(item.status).toBe('pending');
    expect(item.attempts).toBe(0);
    expect(item.deviceId).toBe('dev-001');
    expect(item.deviceType).toBe('laptop');

    const all = await syncQueueStorage.getAll();
    expect(all).toHaveLength(1);
    expect(all[0].id).toBe(item.id);
  });

  it('updates an item in place, preserving other fields', async () => {
    const item = await syncQueueStorage.enqueue('dev-002', 'monitor');
    await syncQueueStorage.update(item.id, { status: 'failed', attempts: 5, lastError: 'boom' });

    const [updated] = await syncQueueStorage.getAll();
    expect(updated.status).toBe('failed');
    expect(updated.attempts).toBe(5);
    expect(updated.lastError).toBe('boom');
    expect(updated.deviceId).toBe('dev-002');
  });

  it('removes an item by id without affecting others', async () => {
    const a = await syncQueueStorage.enqueue('dev-a', 'laptop');
    const b = await syncQueueStorage.enqueue('dev-b', 'printer');

    await syncQueueStorage.remove(a.id);

    const all = await syncQueueStorage.getAll();
    expect(all).toHaveLength(1);
    expect(all[0].id).toBe(b.id);
  });

  it('returns an empty array if the stored value is corrupted JSON', async () => {
    await AsyncStorage.setItem('ecotrace_collector_sync_queue_v1', 'not-json');
    expect(await syncQueueStorage.getAll()).toEqual([]);
  });
});
