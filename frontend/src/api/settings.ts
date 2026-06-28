import { http } from './client';
import type { ConnectionResult, PojuConfigOut, TokenUpdate } from './types';

/**
 * 破局接口配置 API。
 *
 * - GET  /api/settings/poju         获取配置（token 脱敏）
 * - PUT  /api/settings/poju/token   更新 Token
 * - PUT  /api/settings/poju/base-url 更新 base_url（支持置空，传 null/空字符串）
 * - POST /api/settings/poju/test    测试连接
 */

export function getPojuConfig() {
  return http.get<PojuConfigOut>('/settings/poju').then((r) => r.data);
}

export function updatePojuToken(payload: TokenUpdate) {
  return http.put<PojuConfigOut>('/settings/poju/token', payload).then((r) => r.data);
}

/**
 * 更新破局 base_url。``baseUrl`` 传 ``null`` 或空字符串表示清除。
 */
export function updatePojuBaseUrl(baseUrl: string | null) {
  return http
    .put<PojuConfigOut>('/settings/poju/base-url', { base_url: baseUrl ?? null })
    .then((r) => r.data);
}

export function testPojuConnection() {
  return http.post<ConnectionResult>('/settings/poju/test').then((r) => r.data);
}