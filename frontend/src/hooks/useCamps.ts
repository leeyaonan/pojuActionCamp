import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as campsApi from '@/api/camps';
import type { CampCreate, CampUpdate } from '@/api/types';
import { toastOnBizError } from '@/api/client';

// query keys 统一在此导出，便于 invalidate
export const campKeys = {
  all: ['camps'] as const,
  detail: (id: number) => ['camp', id] as const,
};

/** 行动营列表 */
export function useCamps() {
  return useQuery({
    queryKey: campKeys.all,
    queryFn: campsApi.listCamps,
  });
}

/** 行动营详情 */
export function useCamp(id?: number) {
  return useQuery({
    queryKey: id ? campKeys.detail(id) : ['camp', 'none'],
    queryFn: () => campsApi.getCamp(id as number),
    enabled: !!id,
  });
}

/** 创建行动营 */
export function useCreateCamp() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: CampCreate) => campsApi.createCamp(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: campKeys.all });
    },
    onError: (err) => {
      toastOnBizError(err);
    },
  });
}

/** 更新行动营 */
export function useUpdateCamp() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: CampUpdate }) =>
      campsApi.updateCamp(id, payload),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: campKeys.all });
      qc.invalidateQueries({ queryKey: campKeys.detail(vars.id) });
    },
    onError: (err) => {
      toastOnBizError(err);
    },
  });
}

/** 删除行动营 */
export function useDeleteCamp() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => campsApi.deleteCamp(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: campKeys.all });
    },
    onError: (err) => {
      toastOnBizError(err);
    },
  });
}