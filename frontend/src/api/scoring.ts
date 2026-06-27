import { http } from './client';
import type { ScoringOut, ScoringUpdate } from './types';

/**
 * 评分标准 API（全局唯一 active）。
 *
 * - GET  /api/scoring
 * - PUT  /api/scoring
 */

export function getScoring() {
  return http.get<ScoringOut>('/scoring').then((r) => r.data);
}

export function updateScoring(payload: ScoringUpdate) {
  return http.put<ScoringOut>('/scoring', payload).then((r) => r.data);
}