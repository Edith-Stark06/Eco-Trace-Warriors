import AsyncStorage from '@react-native-async-storage/async-storage';
import type { SyncQueueItem } from '../types/syncQueue';

const QUEUE_KEY = 'ecotrace_collector_sync_queue_v1';

/**
 * Local-first queue of AI device confirmations captured while offline —
 * AsyncStorage-backed (plain, non-sensitive data), matching the Flutter
 * app's sqflite-backed queue. An item is appended immediately on capture
 * and only removed once device_ai confirms the finalize call succeeded.
 */
export const syncQueueStorage = {
  async getAll(): Promise<SyncQueueItem[]> {
    const raw = await AsyncStorage.getItem(QUEUE_KEY);
    if (!raw) return [];
    try {
      return JSON.parse(raw) as SyncQueueItem[];
    } catch {
      return [];
    }
  },

  async enqueue(deviceId: string, deviceType: string): Promise<SyncQueueItem> {
    const items = await syncQueueStorage.getAll();
    const item: SyncQueueItem = {
      id: `queue-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      deviceId,
      deviceType,
      status: 'pending',
      attempts: 0,
      lastError: null,
      createdAt: new Date().toISOString(),
      nextRetryAt: null,
    };
    await AsyncStorage.setItem(QUEUE_KEY, JSON.stringify([...items, item]));
    return item;
  },

  async update(id: string, patch: Partial<SyncQueueItem>): Promise<void> {
    const items = await syncQueueStorage.getAll();
    const next = items.map((item) => (item.id === id ? { ...item, ...patch } : item));
    await AsyncStorage.setItem(QUEUE_KEY, JSON.stringify(next));
  },

  async remove(id: string): Promise<void> {
    const items = await syncQueueStorage.getAll();
    await AsyncStorage.setItem(QUEUE_KEY, JSON.stringify(items.filter((item) => item.id !== id)));
  },
};
