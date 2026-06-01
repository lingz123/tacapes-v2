/**
 * Shared MSW server for component tests. Per-test handlers are layered with
 * `server.use(...)`; the base set here returns an empty mission list so a
 * test that forgets to seed gets a predictable empty page rather than a 404.
 */
import { setupServer } from 'msw/node';
import { http, HttpResponse } from 'msw';

import type {
  MissionListResponse,
  MissionDetail,
  CreateMissionResponse,
} from '@/types/api';

export const emptyList: MissionListResponse = {
  missions: [],
  aggregate: {
    invested: 0,
    current_value: 0,
    pnl_pct: null,
    cost: 0,
    unpriced_count: 0,
  },
};

export const server = setupServer(
  http.get('/api/missions', () => HttpResponse.json(emptyList)),
);

export { http, HttpResponse };
export type { MissionListResponse, MissionDetail, CreateMissionResponse };
