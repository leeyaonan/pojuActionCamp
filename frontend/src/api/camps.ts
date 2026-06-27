import { http } from './client';
import type { CampCreate, CampOut, CampSummary, CampUpdate } from './types';

/**
 * 行动营 API。
 *
 * - GET    /api/camps       列表（含运行期状态/进度）
 * - POST   /api/camps       创建
 * - GET    /api/camps/{id}  详情
 * - PUT    /api/camps/{id}  部分更新
 * - DELETE /api/camps/{id}  软删除
 */

export function listCamps() {
  return http.get<CampSummary[]>('/camps').then((r) => r.data);
}

export function createCamp(payload: CampCreate) {
  return http.post<CampOut>('/camps', payload).then((r) => r.data);
}

export function getCamp(id: number) {
  return http.get<CampOut>(`/camps/${id}`).then((r) => r.data);
}

export function updateCamp(id: number, payload: CampUpdate) {
  return http.put<CampOut>(`/camps/${id}`, payload).then((r) => r.data);
}

export function deleteCamp(id: number) {
  return http.delete<{ camp_id: number; deleted: boolean }>(`/camps/${id}`).then((r) => r.data);
}