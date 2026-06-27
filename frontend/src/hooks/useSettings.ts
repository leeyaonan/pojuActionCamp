import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as settingsApi from '@/api/settings';
import { toastOnBizError } from '@/api/client';

// query keys 统一在此导出，便于 invalidate
export const settingsKeys = {
  poju: ['settings', 'poju'] as const,
};

/** 获取破局接口配置 */
export function usePojuConfig() {
  return useQuery({
    queryKey: settingsKeys.poju,
    queryFn: settingsApi.getPojuConfig,
  });
}

/** 更新 Token */
export function useUpdateToken() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (token: string) => settingsApi.updatePojuToken({ token }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: settingsKeys.poju });
    },
    onError: (err) => {
      toastOnBizError(err);
    },
  });
}

/** 测试连接 */
export function useTestConnection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => settingsApi.testPojuConnection(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: settingsKeys.poju });
    },
    onError: (err) => {
      toastOnBizError(err);
    },
  });
}