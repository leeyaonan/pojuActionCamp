import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as volunteerApi from '@/api/volunteer';
import type {
  GradeConfirmIn,
  GradeDraftOut,
  StudentStatus,
} from '@/api/types';
import { toastOnBizError } from '@/api/client';

export const volunteerKeys = {
  students: (campId: number, status?: StudentStatus) =>
    ['students', campId, status ?? 'all'] as const,
  archive: (studentId: number) => ['student-archive', studentId] as const,
  pending: (campId: number) => ['pending-grades', campId] as const,
  gradeDraft: (checkinId: number) => ['grade-draft', checkinId] as const,
  reminders: (campId: number) => ['reminders', campId] as const,
};

/** 学员看板列表 */
export function useStudents(campId?: number, status?: StudentStatus) {
  return useQuery({
    queryKey: volunteerKeys.students(campId ?? -1, status),
    queryFn: () => volunteerApi.listStudents(campId as number, status),
    enabled: !!campId,
  });
}

/** 学员档案 */
export function useStudentArchive(studentId?: number) {
  return useQuery({
    queryKey: volunteerKeys.archive(studentId ?? -1),
    queryFn: () => volunteerApi.getStudentArchive(studentId as number),
    enabled: !!studentId,
  });
}

/** 待评改列表 */
export function usePendingGrades(campId?: number) {
  return useQuery({
    queryKey: volunteerKeys.pending(campId ?? -1),
    queryFn: () => volunteerApi.listPendingGrades(campId as number),
    enabled: !!campId,
  });
}

/** 待提醒列表（实时拉取破局，不入缓存太久） */
export function useReminders(campId?: number) {
  return useQuery({
    queryKey: volunteerKeys.reminders(campId ?? -1),
    queryFn: () => volunteerApi.listReminders(campId as number),
    enabled: !!campId,
    // 待提醒状态变化频繁，进入 tab 即拉一次；不设 staleTime，每次切换 tab 重拉
    staleTime: 0,
    refetchOnMount: 'always',
  });
}

/**
 * 评改草稿（按 checkinId 缓存）。
 *
 * 实现说明：
 *  - 后端没有独立的"获取评改草稿"接口，草稿由 useGenerateGrade / useRegenerateGrade
 *    生成后写入 React Query 缓存（key: ['grade-draft', checkinId]）。
 *  - 该 hook 仅消费缓存，存在即返回，不存在则返回 undefined（由页面触发 generate）。
 *  - 通过 useQueryClient + select 拿到当前缓存值并响应式更新（subscribe）。
 */
export function useGradeDraft(checkinId?: number): GradeDraftOut | undefined {
  const qc = useQueryClient();
  // 直接订阅 cache：cache 内容变化时组件会重渲染
  return qc.getQueryData<GradeDraftOut>(volunteerKeys.gradeDraft(checkinId ?? -1));
}

/** 手动同步 */
export function useSyncBoard(campId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => volunteerApi.syncBoard(campId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: volunteerKeys.students(campId) });
    },
    onError: (err) => {
      toastOnBizError(err);
    },
  });
}

/**
 * 初始化学员档案 mutation（拉破局 query-people）。
 *
 * 成功 → 刷新学员列表（全部 status 维度）+ 自动 inspect `result.errors`，
 * 由 Dashboard 通过 Modal.info 决定是否展开明细。
 *
 * 注：useQuery 的 key 含 status（all/ongoing/unqualified/qualified），要
 * 刷新所有变体用 prefix `['students', campId]` 精确 prefix 匹配。
 */
export function useInitArchive(campId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => volunteerApi.initStudentArchive(campId),
    onSuccess: () => {
      // prefix 匹配：['students', campId, *] 全部失效
      qc.invalidateQueries({ queryKey: ['students', campId] });
    },
    onError: (err) => {
      toastOnBizError(err);
    },
  });
}

/** 刷新学员档案（同 useInitArchive，复用 InitResult；UI 区分按钮文案） */
export function useRefreshArchive(campId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => volunteerApi.refreshStudentArchive(campId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['students', campId] });
    },
    onError: (err) => {
      toastOnBizError(err);
    },
  });
}

/** 生成评改草稿 */
export function useGenerateGrade() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (checkinId: number) =>
      volunteerApi.generateGrade({ checkin_id: checkinId }),
    onSuccess: (data, checkinId) => {
      // 写入 cache，供 useGradeDraft 消费
      qc.setQueryData(volunteerKeys.gradeDraft(checkinId), data);
    },
    onError: (err) => {
      toastOnBizError(err);
    },
  });
}

/** 重新生成评改 */
export function useRegenerateGrade() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (checkinId: number) =>
      volunteerApi.regenerateGrade({ checkin_id: checkinId }),
    onSuccess: (data, checkinId) => {
      qc.setQueryData(volunteerKeys.gradeDraft(checkinId), data);
    },
    onError: (err) => {
      toastOnBizError(err);
    },
  });
}

/** 确认并同步评改 */
export function useConfirmGrade(campId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: GradeConfirmIn) => volunteerApi.confirmGrade(payload),
    onSuccess: (_data, vars) => {
      // 评改成功后清除对应草稿 cache
      qc.removeQueries({ queryKey: volunteerKeys.gradeDraft(vars.checkin_id) });
      qc.invalidateQueries({ queryKey: volunteerKeys.pending(campId) });
      qc.invalidateQueries({ queryKey: volunteerKeys.students(campId) });
    },
    onError: (err) => {
      toastOnBizError(err);
    },
  });
}

/** 仅保存评改（不同步破局）— BUG-VOL-006 */
export function useSaveGradeDraft(campId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: GradeConfirmIn) => volunteerApi.saveGradeDraft(payload),
    onSuccess: (_data, vars) => {
      // 评改已落本地，清草稿 cache 并刷新待评改列表
      qc.removeQueries({ queryKey: volunteerKeys.gradeDraft(vars.checkin_id) });
      qc.invalidateQueries({ queryKey: volunteerKeys.pending(campId) });
      qc.invalidateQueries({ queryKey: volunteerKeys.students(campId) });
    },
    onError: (err) => {
      toastOnBizError(err);
    },
  });
}

/** 重试评改同步 */
export function useRetryGradeSync(campId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (checkinId: number) => volunteerApi.retryGradeSync(checkinId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: volunteerKeys.pending(campId) });
    },
    onError: (err) => {
      toastOnBizError(err);
    },
  });
}
