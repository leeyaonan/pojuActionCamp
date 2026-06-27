import { http } from './client';
import type {
  CheckinDraftOut,
  CheckinGenerateIn,
  CheckinRecordOut,
  CheckinSubmitIn,
  CheckinSubmitResult,
  DayTaskOut,
  DayTaskUpdate,
  RouteOut,
  TodayOut,
} from './types';

/**
 * 学员端 API（学习路线 + 打卡）。
 *
 * - POST /api/camps/{id}/route/generate     生成学习路线
 * - GET  /api/camps/{id}/route              获取学习路线
 * - POST /api/camps/{id}/route/regenerate   重新规划
 * - PUT  /api/route/tasks/{taskId}          编辑每日任务
 * - GET  /api/camps/{id}/today              今日任务
 * - POST /api/camps/{id}/checkin/generate    生成打卡草稿
 * - POST /api/camps/{id}/checkin/submit     提交打卡
 * - GET  /api/camps/{id}/checkins           打卡记录列表
 */

export function generateRoute(campId: number) {
  return http.post<RouteOut>(`/camps/${campId}/route/generate`).then((r) => r.data);
}

export function getRoute(campId: number) {
  return http.get<RouteOut | null>(`/camps/${campId}/route`).then((r) => r.data);
}

export function regenerateRoute(campId: number, keepEdits = true) {
  return http
    .post<RouteOut>(`/camps/${campId}/route/regenerate`, null, {
      params: { keep_edits: keepEdits },
    })
    .then((r) => r.data);
}

export function updateDayTask(taskId: number, payload: DayTaskUpdate) {
  return http.put<DayTaskOut>(`/route/tasks/${taskId}`, payload).then((r) => r.data);
}

export function getToday(campId: number, today?: string) {
  return http
    .get<TodayOut>(`/camps/${campId}/today`, { params: today ? { today } : undefined })
    .then((r) => r.data);
}

export function generateCheckin(campId: number, payload: CheckinGenerateIn) {
  return http.post<CheckinDraftOut>(`/camps/${campId}/checkin/generate`, payload).then((r) => r.data);
}

export function submitCheckin(campId: number, payload: CheckinSubmitIn) {
  return http.post<CheckinSubmitResult>(`/camps/${campId}/checkin/submit`, payload).then((r) => r.data);
}

export function listCheckins(campId: number) {
  return http.get<CheckinRecordOut[]>(`/camps/${campId}/checkins`).then((r) => r.data);
}