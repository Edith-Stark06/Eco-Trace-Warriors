import AsyncStorage from '@react-native-async-storage/async-storage';
import { syncQueueStorage } from './syncQueue';
import type { CreateSubmissionInput } from '../types/submission';

const SAMPLE_INPUT: CreateSubmissionInput = {
  category: 'laptop',
  estimatedWeight: 2.5,
  address: '12 Green Street',
  latitude: 13.08,
  longitude: 80.27,
};

describe('syncQueueStorage', () => {
  beforeEach(async () => {
    await AsyncStorage.clear();
  });

  it('starts empty', async () => {
    expect(await syncQueueStorage.getAll()).toEqual([]);
  });

  it('enqueues a waste report with pending status', async () => {
    const item = await syncQueueStorage.enqueue(SAMPLE_INPUT);
    expect(item.status).toBe('pending');
    expect(item.attempts).toBe(0);
    expect(item.input).toEqual(SAMPLE_INPUT);

    const all = await syncQueueStorage.getAll();
    expect(all).toHaveLength(1);
  });

  it('updates an item in place after a failed sync attempt', async () => {
    const item = await syncQueueStorage.enqueue(SAMPLE_INPUT);
    await syncQueueStorage.update(item.id, { status: 'failed', attempts: 5, lastError: 'Validation failed' });

    const [updated] = await syncQueueStorage.getAll();
    expect(updated.status).toBe('failed');
    expect(updated.attempts).toBe(5);
    expect(updated.lastError).toBe('Validation failed');
  });

  it('removes an item by id without affecting others', async () => {
    const a = await syncQueueStorage.enqueue(SAMPLE_INPUT);
    const b = await syncQueueStorage.enqueue({ ...SAMPLE_INPUT, category: 'monitor' });

    await syncQueueStorage.remove(a.id);

    const all = await syncQueueStorage.getAll();
    expect(all).toHaveLength(1);
    expect(all[0].id).toBe(b.id);
  });
});
