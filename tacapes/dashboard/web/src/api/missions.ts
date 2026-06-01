/**
 * TanStack Query hooks for the `/api/missions/*` endpoints.
 *
 * Conventions:
 * - One query key namespace, `['missions']`, with per-mission detail keyed
 *   off `['missions', id]`. Mutations invalidate the right subset rather
 *   than blowing away the whole namespace.
 * - All fetchers throw on non-2xx so React Query treats them as errors.
 *   The error message preserves the FastAPI `detail` body when present.
 * - All endpoints called with absolute `/api/...` paths so the Vite proxy
 *   in dev and the same-origin mount in prod both work without config.
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationOptions,
} from '@tanstack/react-query';

import type {
  CreateMissionRequest,
  CreateMissionResponse,
  MissionDetail,
  MissionListResponse,
  MissionStatusResponse,
} from '@/types/api';

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = 'ApiError';
  }
}

async function readError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: string };
    if (body?.detail) return body.detail;
  } catch {
    // body wasn't JSON; fall through
  }
  return response.statusText || `HTTP ${response.status}`;
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    throw new ApiError(response.status, await readError(response));
  }
  return (await response.json()) as T;
}

async function postJson<TBody, TResponse>(
  path: string,
  body: TBody,
): Promise<TResponse> {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new ApiError(response.status, await readError(response));
  }
  if (response.status === 204) return undefined as TResponse;
  return (await response.json()) as TResponse;
}

async function deleteJson(path: string): Promise<void> {
  const response = await fetch(path, { method: 'DELETE' });
  if (!response.ok) {
    throw new ApiError(response.status, await readError(response));
  }
}

export const missionKeys = {
  all: ['missions'] as const,
  list: () => [...missionKeys.all, 'list'] as const,
  detail: (id: string) => [...missionKeys.all, 'detail', id] as const,
  status: (id: string) => [...missionKeys.all, 'status', id] as const,
};

/** Fetches the mission list + aggregate stats for the index page. */
export function useMissionList() {
  return useQuery<MissionListResponse>({
    queryKey: missionKeys.list(),
    queryFn: () => getJson<MissionListResponse>('/api/missions'),
  });
}

/** Loads a single mission detail. Used by the detail page in Phase 5. */
export function useMissionDetail(id: string | undefined) {
  return useQuery<MissionDetail>({
    queryKey: id ? missionKeys.detail(id) : ['missions', 'detail', '__missing__'],
    queryFn: () => getJson<MissionDetail>(`/api/missions/${id!}`),
    enabled: Boolean(id),
  });
}

/**
 * Polls `/api/missions/:id/status` every 3 seconds while the mission is in
 * a non-terminal state (`queued` or `running`), then settles into a single
 * fetch once `done` or `failed` arrive. When the status flips to `done`,
 * the detail-page query is invalidated so the heavy payload refreshes
 * exactly once instead of being polled in lockstep.
 *
 * Returns a normal `useQuery` result so callers can branch on `data.status`
 * without re-implementing the polling machinery.
 */
export function useMissionStatus(id: string | undefined) {
  const qc = useQueryClient();
  return useQuery<MissionStatusResponse>({
    queryKey: id ? missionKeys.status(id) : ['missions', 'status', '__missing__'],
    queryFn: async () => {
      const data = await getJson<MissionStatusResponse>(`/api/missions/${id!}/status`);
      // Pull the full record once the pipeline lands. Re-fetching after a
      // failure also lets the detail view show `error_message`.
      if (id && (data.status === 'done' || data.status === 'failed')) {
        qc.invalidateQueries({ queryKey: missionKeys.detail(id) });
      }
      return data;
    },
    enabled: Boolean(id),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'queued' || status === 'running' ? 3000 : false;
    },
  });
}

/**
 * Creates a mission. Invalidates the list on success so the new row appears
 * after the dialog closes. The caller (NewMissionDialog) is responsible for
 * navigating to the detail page using the returned id.
 */
export function useCreateMission(
  options?: UseMutationOptions<CreateMissionResponse, Error, CreateMissionRequest>,
) {
  const qc = useQueryClient();
  return useMutation<CreateMissionResponse, Error, CreateMissionRequest>({
    mutationFn: (payload) =>
      postJson<CreateMissionRequest, CreateMissionResponse>('/api/missions', payload),
    onSuccess: (data, vars, onMutateRes, ctx) => {
      qc.invalidateQueries({ queryKey: missionKeys.list() });
      options?.onSuccess?.(data, vars, onMutateRes, ctx);
    },
    ...options,
  });
}

/**
 * Deletes a mission. Optimistically removes from the list cache; rolls back
 * on failure. Detail-page cache for the id is invalidated regardless so a
 * navigate-back doesn't show stale data.
 */
export function useDeleteMission(
  options?: UseMutationOptions<void, Error, string>,
) {
  const qc = useQueryClient();
  return useMutation<void, Error, string, { previous?: MissionListResponse }>({
    mutationFn: (id) => deleteJson(`/api/missions/${id}`),
    onMutate: async (id) => {
      await qc.cancelQueries({ queryKey: missionKeys.list() });
      const previous = qc.getQueryData<MissionListResponse>(missionKeys.list());
      if (previous) {
        qc.setQueryData<MissionListResponse>(missionKeys.list(), {
          ...previous,
          missions: previous.missions.filter((m) => m.id !== id),
        });
      }
      return { previous };
    },
    onError: (_err, _id, ctx) => {
      if (ctx?.previous) qc.setQueryData(missionKeys.list(), ctx.previous);
    },
    onSettled: (_data, _err, id) => {
      qc.invalidateQueries({ queryKey: missionKeys.list() });
      qc.invalidateQueries({ queryKey: missionKeys.detail(id) });
    },
    ...(options as UseMutationOptions<void, Error, string, { previous?: MissionListResponse }>),
  });
}

/**
 * Refreshes the price cache server-side, then re-fetches mission lists and
 * the currently open detail page so P&L pills update.
 */
export function useRefreshPrices(options?: UseMutationOptions<void, Error, void>) {
  const qc = useQueryClient();
  return useMutation<void, Error, void>({
    mutationFn: () => postJson<void, void>('/api/prices/refresh', undefined as unknown as void),
    onSuccess: (data, vars, onMutateRes, ctx) => {
      qc.invalidateQueries({ queryKey: missionKeys.all });
      options?.onSuccess?.(data, vars, onMutateRes, ctx);
    },
    ...options,
  });
}

export { ApiError };
