import { http } from './client';
import type {
  GradeConfirmIn,
  GradeDraftOut,
  GradeGenerateIn,
  GradeSaveDraftIn,
  PendingGradeOut,
  StudentArchive,
  StudentStatus,
  StudentSummary,
  SyncResult,
} from './types';

/**
 * 志愿者端 API（学员看板、档案、评改）。
 *
 * - POST /api/volunteer/camps/{id}/sync              手动同步
 * - GET  /api/volunteer/camps/{id}/students          学员看板列表
 * - GET  /api/volunteer/students/{id}                学员档案
 * - GET  /api/volunteer/camps/{id}/grades/pending    待评改列表
 * - POST /api/volunteer/grades/generate              生成评改
 * - POST /api/volunteer/grades/confirm               确认并同步
 * - POST /api/volunteer/grades/save-draft            仅保存（不同步破局）— BUG-VOL-006
 * - POST /api/volunteer/grades/{checkinId}/retry     重试同步
 * - POST /api/volunteer/grades/regenerate            重新生成评改
 */

export function syncBoard(campId: number) {
  return http.post<SyncResult>(`/volunteer/camps/${campId}/sync`).then((r) => r.data);
}

export function listStudents(campId: number, status?: StudentStatus) {
  return http
    .get<StudentSummary[]>(`/volunteer/camps/${campId}/students`, { params: status ? { status } : undefined })
    .then((r) => r.data);
}

export function getStudentArchive(studentId: number) {
  return http.get<StudentArchive>(`/volunteer/students/${studentId}`).then((r) => r.data);
}

export function listPendingGrades(campId: number) {
  return http.get<PendingGradeOut[]>(`/volunteer/camps/${campId}/grades/pending`).then((r) => r.data);
}

export function generateGrade(payload: GradeGenerateIn) {
  return http.post<GradeDraftOut>('/volunteer/grades/generate', payload).then((r) => r.data);
}

export function confirmGrade(payload: GradeConfirmIn) {
  return http.post<SyncResult>('/volunteer/grades/confirm', payload).then((r) => r.data);
}

export function saveGradeDraft(payload: GradeSaveDraftIn) {
  return http.post<SyncResult>('/volunteer/grades/save-draft', payload).then((r) => r.data);
}

export function retryGradeSync(checkinId: number) {
  return http.post<SyncResult>(`/volunteer/grades/${checkinId}/retry`).then((r) => r.data);
}

export function regenerateGrade(payload: GradeGenerateIn) {
  return http.post<GradeDraftOut>('/volunteer/grades/regenerate', payload).then((r) => r.data);
}