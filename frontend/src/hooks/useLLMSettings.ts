import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as llmApi from '@/api/llmSettings';
import { toastOnBizError } from '@/api/client';
import type { LlmProviderCreate, LlmProviderUpdate } from '@/api/types';

// query keys 统一导出，便于 invalidate
export const llmKeys = {
  providers: ['llm', 'providers'] as const,
  active: ['llm', 'active'] as const,
};

/** 列出所有厂商配置 */
export function useLLMProviders() {
  return useQuery({
    queryKey: llmKeys.providers,
    queryFn: llmApi.listLlmProviders,
  });
}

/** 当前激活厂商（供「当前使用」卡） */
export function useLLMActive() {
  return useQuery({
    queryKey: llmKeys.active,
    queryFn: llmApi.getLlmActive,
  });
}

/** 新增厂商 */
export function useCreateProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: LlmProviderCreate) => llmApi.createLlmProvider(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: llmKeys.providers }),
    onError: (err) => toastOnBizError(err),
  });
}

/** 更新厂商（配置变更后 active 也可能变，一并 invalidate） */
export function useUpdateProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: LlmProviderUpdate }) =>
      llmApi.updateLlmProvider(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: llmKeys.providers });
      qc.invalidateQueries({ queryKey: llmKeys.active });
    },
    onError: (err) => toastOnBizError(err),
  });
}

/** 删除厂商 */
export function useDeleteProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => llmApi.deleteLlmProvider(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: llmKeys.providers });
      qc.invalidateQueries({ queryKey: llmKeys.active });
    },
    onError: (err) => toastOnBizError(err),
  });
}

/** 测试连接（成功/失败结果由调用方按 result.valid 判断，hook 仅 invalidate） */
export function useTestProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => llmApi.testLlmProvider(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: llmKeys.providers }),
    onError: (err) => toastOnBizError(err),
  });
}

/** 激活厂商 */
export function useActivateProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => llmApi.activateLlmProvider(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: llmKeys.providers });
      qc.invalidateQueries({ queryKey: llmKeys.active });
    },
    onError: (err) => toastOnBizError(err),
  });
}
