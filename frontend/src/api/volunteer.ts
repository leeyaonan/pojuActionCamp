import { http } from './client';
import type {
  GradeConfirmIn,
  GradeDraftOut,
  GradeGenerateIn,
  PendingGradeOut,
  StudentArchive,
  StudentStatus,
  StudentSummary,
  SyncResult,
} from './types';

/**
 * 志愿者端 API（学员看板、档案、评改）。
 *
 * - POST /api/camps/{id}/sync              手动同步
 * - GET  /api/camps/{id}/students          学员看板列表
 * - GET  /api/students/{id}                学员档案
 * - GET  /api/camps/{id}/grades/pending    待评改列表
 * - POST /api/grades/generate              生成评改
 * - POST /api/grades/confirm               确认并同步
 * - POST /api/grades/{checkinId}/retry     重试同步
 * - POST /api/grades/regenerate            重新生成评改
 */

export function syncBoard(campId: number) {
  return http.post<SyncResult>(`/camps/${campId}/sync`).then((r) => r.data);
}

export function listStudents(campId: number, status?: StudentStatus) {
  return http
    .get<StudentSummary[]>(`/camps/${campId}/students`, { params: status ? { status } : undefined })
    .then((r) => r.data);
}

export function getStudentArchive(studentId: number) {
  return http.get<StudentArchive>(`/students/${studentId}`).then((r) => r.data);
}

export function listPendingGrades(campId: number) {
  return http.get<PendingGradeOut[]>(`/camps/${campId}/grades/pending`).then((r) => r.data);
}

export function generateGrade(payload: GradeGenerateIn) {
  return http.post<GradeDraftOut>('/grades/generate', payload).then((r) => r.data);
}

export function confirmGrade(payload: GradeConfirmIn) {
  return http.post<SyncResult>('/grades/confirm', payload).then((r) => r.data);
}

export function retryGradeSync(checkinId: number) {
  return http.post<SyncResult>(`/grades/${checkinId}/retry`).then((r) => r.data);
}

export function regenerateGrade(payload: GradeGenerateIn) {
  return http.post<GradeDraftOut>('/grades/regenerate', payload).then((r) => r.data);
}