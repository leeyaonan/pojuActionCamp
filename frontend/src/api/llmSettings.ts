import { http } from './client';
import type {
  ConnectionResult,
  LlmActiveOut,
  LlmProviderCreate,
  LlmProviderOut,
  LlmProviderUpdate,
} from './types';

/**
 * 大模型厂商配置 API。
 *
 * - GET    /api/settings/llm/providers            列出厂商（Key 脱敏）
 * - POST   /api/settings/llm/providers            新增厂商
 * - PUT    /api/settings/llm/providers/{id}       更新厂商
 * - DELETE /api/settings/llm/providers/{id}       删除厂商（预置禁删）
 * - POST   /api/settings/llm/providers/{id}/test  测试连接
 * - POST   /api/settings/llm/providers/{id}/activate 激活厂商
 * - GET    /api/settings/llm/active               当前激活厂商
 */

export function listLlmProviders() {
  return http
    .get<LlmProviderOut[]>('/settings/llm/providers')
    .then((r) => r.data);
}

export function createLlmProvider(payload: LlmProviderCreate) {
  return http
    .post<LlmProviderOut>('/settings/llm/providers', payload)
    .then((r) => r.data);
}

export function updateLlmProvider(id: number, payload: LlmProviderUpdate) {
  return http
    .put<LlmProviderOut>(`/settings/llm/providers/${id}`, payload)
    .then((r) => r.data);
}

export function deleteLlmProvider(id: number) {
  return http
    .delete<void>(`/settings/llm/providers/${id}`)
    .then((r) => r.data);
}

export function testLlmProvider(id: number) {
  return http
    .post<ConnectionResult>(`/settings/llm/providers/${id}/test`)
    .then((r) => r.data);
}

export function activateLlmProvider(id: number) {
  return http
    .post<LlmProviderOut>(`/settings/llm/providers/${id}/activate`)
    .then((r) => r.data);
}

export function getLlmActive() {
  return http
    .get<LlmActiveOut>('/settings/llm/active')
    .then((r) => r.data);
}
