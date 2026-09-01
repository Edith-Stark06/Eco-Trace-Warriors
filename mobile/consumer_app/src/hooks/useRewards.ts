import { useCallback, useEffect, useState } from 'react';
import { rewardsApi } from '../api/rewardsApi';
import { ApiError } from '../api/ApiError';
import type { RewardBalance, RewardTransactionWithSubmission } from '../types/rewards';

interface State {
  status: 'loading' | 'ready' | 'error';
  balance: RewardBalance | null;
  history: RewardTransactionWithSubmission[];
  error: string | null;
}

const INITIAL_STATE: State = { status: 'loading', balance: null, history: [], error: null };

async function fetchRewards(): Promise<State> {
  try {
    const [balance, history] = await Promise.all([rewardsApi.balance(), rewardsApi.history()]);
    return { status: 'ready', balance, history: [...history], error: null };
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Unable to load rewards.';
    return { status: 'error', balance: null, history: [], error: message };
  }
}

export function useRewards() {
  const [state, setState] = useState<State>(INITIAL_STATE);

  const refresh = useCallback(async () => {
    setState(await fetchRewards());
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchRewards().then((next) => {
      if (!cancelled) setState(next);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return { ...state, refresh };
}
