import { useCallback, useEffect, useState } from 'react';
import { submissionsApi } from '../api/submissionsApi';
import { ApiError } from '../api/ApiError';
import type { PublicSubmission } from '../types/submission';

interface State {
  status: 'loading' | 'ready' | 'error';
  submissions: PublicSubmission[];
  error: string | null;
}

const INITIAL_STATE: State = { status: 'loading', submissions: [], error: null };

async function fetchSubmissions(): Promise<State> {
  try {
    const submissions = await submissionsApi.list();
    return { status: 'ready', submissions: [...submissions], error: null };
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Unable to load your submissions.';
    return { status: 'error', submissions: [], error: message };
  }
}

export function useSubmissions() {
  const [state, setState] = useState<State>(INITIAL_STATE);

  const refresh = useCallback(async () => {
    setState(await fetchSubmissions());
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchSubmissions().then((next) => {
      if (!cancelled) setState(next);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return { ...state, refresh };
}
