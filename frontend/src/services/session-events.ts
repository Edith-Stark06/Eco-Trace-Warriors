/**
 * Auth session event bus.
 *
 * A tiny, framework-agnostic emitter that lets low-level modules (the Axios
 * response interceptor) signal session lifecycle events without importing
 * React, the router, or the auth provider — keeping the dependency direction
 * clean (infrastructure never depends on UI).
 *
 * Currently the only event is `unauthorized`, emitted when the token refresh
 * flow fails and the session can no longer be recovered. The AuthProvider
 * subscribes and reacts (clears state, lets guards redirect to login).
 */

type SessionEvent = 'unauthorized';
type SessionListener = () => void;

const listeners: Record<SessionEvent, Set<SessionListener>> = {
  unauthorized: new Set(),
};

export const sessionEvents = {
  on(event: SessionEvent, listener: SessionListener): () => void {
    listeners[event].add(listener);
    return () => listeners[event].delete(listener);
  },

  emit(event: SessionEvent): void {
    for (const listener of listeners[event]) {
      listener();
    }
  },
};
