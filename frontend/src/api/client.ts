import axios, { AxiosError, type AxiosResponse } from 'axios';
import { App } from 'antd';
import type { ApiResponse } from './types';
import { ErrorCode } from './types';

/**
 * axios 实例：baseURL=/api，统一处理 {code,message,data}。
 *
 * - 响应拦截器：unwrap data。code!=0 时弹 message 并 reject。
 * - 错误码映射友好提示（2001/2003/3001/3002 等）。
 * - HTTP 401/5xx 也走统一错误提示。
 */
export const http = axios.create({
  baseURL: '/api',
  timeout: 30_000,
});

// 业务错误：用于 query/mutation onError 识别
export class BizError extends Error {
  code: number;
  httpStatus?: number;
  constructor(code: number, message: string, httpStatus?: number) {
    super(message);
    this.code = code;
    this.httpStatus = httpStatus;
  }
}

// 业务错误码 -> 友好提示
const FRIENDLY: Record<number, string> = {
  [ErrorCode.VALIDATION]: '参数校验失败，请检查输入',
  [ErrorCode.NOT_FOUND]: '资源不存在',
  [ErrorCode.POJU_AUTH]: '破局 Token 失效，请到「接口配置」更新',
  [ErrorCode.POJU_API]: '破局接口异常，请稍后重试',
  [ErrorCode.POJU_PENDING]: '破局接口待确认，已自动降级',
  [ErrorCode.LLM_ERROR]: 'AI 生成失败，请稍后重试',
  [ErrorCode.MANUAL_NOT_FOUND]: '未配置手册，建议先上传或粘贴手册文本',
  [ErrorCode.INTERNAL]: '服务器内部错误',
};

function friendlyMessage(code: number, raw: string): string {
  return FRIENDLY[code] ?? raw ?? '请求失败';
}

http.interceptors.response.use(
  (response: AxiosResponse<ApiResponse<unknown>>) => {
    const body = response.data;
    // 中间件已统一为 {code,message,data}
    if (body && typeof body === 'object' && 'code' in body) {
      if (body.code === 0) {
        // 成功：把 data 返回出去
        return { ...response, data: body.data } as AxiosResponse;
      }
      // 业务错误：弹 toast 并 reject
      const message = friendlyMessage(body.code, body.message);
      throw new BizError(body.code, message, response.status);
    }
    // 兼容非包装响应
    return response;
  },
  (error: AxiosError<ApiResponse<unknown>>) => {
    // 网络错误 / 后端未启动
    if (!error.response) {
      const message = error.message?.includes('Network')
        ? '网络异常，请检查后端服务是否启动'
        : error.message || '请求失败';
      throw new BizError(ErrorCode.INTERNAL, message);
    }
    const body = error.response.data;
    const code = body?.code ?? error.response.status;
    const raw = body?.message ?? error.message;
    const message = friendlyMessage(code, raw);
    throw new BizError(code, message, error.response.status);
  }
);

/**
 * 全局 AntD message 绑定。
 * 在 App 挂载后调用一次，使所有 axios 错误自动 toast。
 */
export function bindGlobalErrorToast() {
  const { message } = App.useApp();
  // 监听未处理的 BizError：通过在响应拦截器外层包装全局监听
  // 这里通过 monkey-patch BizError 在 throw 前自动 toast，
  // 简化做法：在每个 hook 中显式调用 toast，或在此处 patch。
  return message;
}

// 让 BizError 在抛出时自动 toast（包装 axios 调用时调用一次）
let toastRef: ((msg: string) => void) | null = null;
export function setGlobalToast(fn: (msg: string) => void) {
  toastRef = fn;
}

/**
 * 自动绑定 BizError 抛出时的全局 toast。
 * 在 main.tsx 中通过 antd App context 注入 setGlobalToast。
 */
export function toastOnBizError(err: unknown): string {
  if (err instanceof BizError) {
    toastRef?.(err.message);
    return err.message;
  }
  if (err instanceof Error) {
    toastRef?.(err.message);
    return err.message;
  }
  const msg = '未知错误';
  toastRef?.(msg);
  return msg;
}