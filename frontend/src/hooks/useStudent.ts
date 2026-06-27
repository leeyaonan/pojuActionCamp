import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as studentApi from '@/api/student';
import type {
  CheckinGenerateIn,
  CheckinSubmitIn,
  DayTaskUpdate,
} from '@/api/types';
import { toastOnBizError } from '@/api/client';

export const studentKeys = {
  route: (campId: number) => ['route', campId] as const,
  today: (campId: number) => ['today', campId] as const,
  checkins: (campId: number) => ['checkins', campId] as const,
};

/** 学习路线 */
export function useRoute(campId?: number) {
  return useQuery({
    queryKey: studentKeys.route(campId ?? -1),
    queryFn: () => studentApi.getRoute(campId as number),
    enabled: !!campId,
  });
}

/** 生成学习路线 */
export function useGenerateRoute(campId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => studentApi.generateRoute(campId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: studentKeys.route(campId) });
      qc.invalidateQueries({ queryKey: studentKeys.today(campId) });
    },
    onError: (err) => {
      toastOnBizError(err);
    },
  });
}

/** 重新规划学习路线 */
export function useRegenerateRoute(campId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (keepEdits: boolean = true) => studentApi.regenerateRoute(campId, keepEdits),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: studentKeys.route(campId) });
      qc.invalidateQueries({ queryKey: studentKeys.today(campId) });
    },
    onError: (err) => {
      toastOnBizError(err);
    },
  });
}

/** 编辑每日任务 */
export function useUpdateDayTask(campId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ taskId, payload }: { taskId: number; payload: DayTaskUpdate }) =>
      studentApi.updateDayTask(taskId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: studentKeys.route(campId) });
      qc.invalidateQueries({ queryKey: studentKeys.today(campId) });
    },
    onError: (err) => {
      toastOnBizError(err);
    },
  });
}

/** 今日任务 */
export function useTodayTasks(campId?: number, today?: string) {
  return useQuery({
    queryKey: [...studentKeys.today(campId ?? -1), today ?? 'today'],
    queryFn: () => studentApi.getToday(campId as number, today),
    enabled: !!campId,
  });
}

/** 生成打卡草稿 */
export function useGenerateCheckin(campId: number) {
  return useMutation({
    mutationFn: (payload: CheckinGenerateIn) => studentApi.generateCheckin(campId, payload),
    onError: (err) => {
      toastOnBizError(err);
    },
  });
}

/** 提交打卡 */
export function useSubmitCheckin(campId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: CheckinSubmitIn) => studentApi.submitCheckin(campId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: studentKeys.checkins(campId) });
    },
    onError: (err) => {
      toastOnBizError(err);
    },
  });
}

/** 打卡记录列表 */
export function useCheckins(campId?: number) {
  return useQuery({
    queryKey: studentKeys.checkins(campId ?? -1),
    queryFn: () => studentApi.listCheckins(campId as number),
    enabled: !!campId,
  });
}