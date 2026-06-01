/**
 * Wire types for the FastAPI dashboard endpoints.
 *
 * These mirror the Pydantic models in `tacapes/dashboard/api/schemas.py`;
 * if the Python side changes shapes, update both files in the same commit.
 * Stage JSONB blobs stay `unknown` here because the React side documents
 * them against `tacapes/schemas/` rather than re-typing the LLM pipeline.
 */

export type MissionStatus = 'queued' | 'running' | 'done' | 'failed';

export interface PositionPnl {
  ticker: string;
  weight_pct: number;
  notional_usd: number;
  rationale: string | null;
  entry_price: number | null;
  entry_price_date: string | null;
  current_price: number | null;
  pnl_pct: number | null;
}

export interface StatStripShape {
  invested: number;
  current_value: number;
  pnl_usd: number | null;
  pnl_pct: number | null;
  unpriced_count: number;
  position_count: number;
  cash_reserve_pct: number;
}

export interface AggregateStats {
  invested: number;
  current_value: number;
  pnl_pct: number | null;
  cost: number;
  unpriced_count: number;
}

export interface MissionListItem {
  id: string;
  statement: string;
  status: MissionStatus;
  created_at: string;
  completed_at: string | null;
  cost_usd: number | null;
  pnl_pct: number | null;
  position_count: number;
}

export interface MissionListResponse {
  missions: MissionListItem[];
  aggregate: AggregateStats;
}

export interface SubthemeSummary {
  id: string;
  name: string;
  description: string | null;
  confidence: number | null;
  candidate_count: number;
  chosen_count: number;
  chosen_tickers: string[];
  passed_tickers: string[];
  key_findings: string[];
}

export interface WeakSpot {
  ticker: string;
  is_fallback_memo: boolean;
  is_momentum_trap: boolean;
  is_losing: boolean;
  current_pnl_pct: number | null;
}

export interface MissionDetail {
  id: string;
  statement: string;
  status: MissionStatus;
  budget_usd: number;
  max_positions: number;
  max_position_pct: number;
  horizon_months: number;
  sectors_excluded: string[];
  allow_shorts: boolean;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  cost_usd: number | null;
  decomposition_json: Record<string, unknown> | null;
  assessments_json: Record<string, unknown> | null;
  shortlist_json: Record<string, unknown> | null;
  ta_outputs_json: Record<string, unknown> | null;
  memos_json: Record<string, unknown> | null;
  portfolio_json: Record<string, unknown> | null;
  positions: PositionPnl[];
  stat_strip: StatStripShape | null;
  subtheme_summary: SubthemeSummary[];
  weak_spots: WeakSpot[];
  chosen_tickers: string[];
}

export interface MissionStatusResponse {
  status: MissionStatus;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
}

export interface CreateMissionRequest {
  statement: string;
  budget_usd: number;
  max_positions: number;
  max_position_pct: number;
  horizon_months: number;
  sectors_excluded: string[];
  allow_shorts: boolean;
}

export interface CreateMissionResponse {
  id: string;
}
