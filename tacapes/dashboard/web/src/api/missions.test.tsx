/**
 * Hook tests for the TanStack Query wrappers.
 *
 * Most behaviour is exercised end-to-end via component tests against the
 * MSW server; this file covers the polling logic in `useMissionStatus`,
 * which is otherwise hard to assert on through a UI test (timer dependent).
 */
import { describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { server, http, HttpResponse } from '@/test/server';
import { useMissionStatus, missionKeys } from './missions';

function makeWrapper(client: QueryClient) {
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

function freshClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
      mutations: { retry: false },
    },
  });
}

describe('useMissionStatus', () => {
  it('settles immediately when status is terminal (no polling)', async () => {
    server.use(
      http.get('/api/missions/m1/status', () =>
        HttpResponse.json({
          status: 'done',
          started_at: null,
          completed_at: null,
          error_message: null,
        }),
      ),
    );

    const client = freshClient();
    const { result } = renderHook(() => useMissionStatus('m1'), {
      wrapper: makeWrapper(client),
    });

    await waitFor(() => expect(result.current.data?.status).toBe('done'));
    // Once `done` is in cache, refetchInterval returns false. We assert that
    // no second hit happens by checking the cache state stays static across
    // a short wait, with no network calls.
    const observed = result.current.dataUpdatedAt;
    await new Promise((r) => setTimeout(r, 50));
    expect(result.current.dataUpdatedAt).toBe(observed);
  });

  it('polls while status is queued, stops when it flips to done', async () => {
    vi.useFakeTimers();
    try {
      let hit = 0;
      server.use(
        http.get('/api/missions/m2/status', () => {
          hit += 1;
          return HttpResponse.json({
            status: hit < 3 ? 'queued' : 'done',
            started_at: null,
            completed_at: null,
            error_message: null,
          });
        }),
      );

      const client = freshClient();
      const { result } = renderHook(() => useMissionStatus('m2'), {
        wrapper: makeWrapper(client),
      });

      // First load is async; flush microtasks to let MSW respond.
      await vi.waitFor(() => expect(result.current.data?.status).toBe('queued'));

      // Advance two 3s intervals; expect two more requests. After hit=3 the
      // server returns `done` and polling should stop.
      await vi.advanceTimersByTimeAsync(3000);
      await vi.waitFor(() => expect(hit).toBeGreaterThanOrEqual(2));
      await vi.advanceTimersByTimeAsync(3000);
      await vi.waitFor(() => expect(result.current.data?.status).toBe('done'));

      // Now advance another 6s; no further hits should fire.
      const finalHits = hit;
      await vi.advanceTimersByTimeAsync(6000);
      expect(hit).toBe(finalHits);
    } finally {
      vi.useRealTimers();
    }
  });

  it('invalidates the detail query when status transitions to done', async () => {
    server.use(
      http.get('/api/missions/m3/status', () =>
        HttpResponse.json({
          status: 'done',
          started_at: null,
          completed_at: null,
          error_message: null,
        }),
      ),
    );

    const client = freshClient();
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries');
    const wrapper = makeWrapper(client);

    const { result } = renderHook(() => useMissionStatus('m3'), { wrapper });

    await waitFor(() => expect(result.current.data?.status).toBe('done'));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: missionKeys.detail('m3') });
  });

  it('is disabled when id is undefined (no network hit)', () => {
    const spy = vi.fn();
    server.use(
      http.get('/api/missions/*/status', () => {
        spy();
        return HttpResponse.json({ status: 'done' });
      }),
    );

    const client = freshClient();
    const { result } = renderHook(() => useMissionStatus(undefined), {
      wrapper: makeWrapper(client),
    });

    expect(result.current.fetchStatus).toBe('idle');
    expect(spy).not.toHaveBeenCalled();
  });
});
