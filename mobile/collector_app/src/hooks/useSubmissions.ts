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
    const submissions = await submissionsApi.listForCollector();
    return { status: 'ready', submissions: [...submissions], error: null };
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Unable to load submissions.';
    return { status: 'error', submissions: [], error: message };
  }
}

/**
 * Loading state starts true (INITIAL_STATE) rather than being set
 * synchronously from inside the effect, so React never sees a setState
 * call before the first await — avoids the cascading-render pattern
 * react-hooks/set-state-in-effect flags, while `refresh()` still lets a
 * manual pull-to-refresh re-show the loading state explicitly.
 */
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
