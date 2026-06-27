import { http } from './client';
import type { ManualWithPreview, PasteIn } from './types';

/**
 * 手册 API。
 *
 * - POST /api/manuals/{campId}/upload   上传文件 (multipart)
 * - POST /api/manuals/{campId}/paste    粘贴文本
 * - GET  /api/manuals/{campId}          元信息 + 预览
 * - DELETE /api/manuals/{campId}        删除
 */

export function getManual(campId: number, n = 500) {
  return http.get<ManualWithPreview>(`/manuals/${campId}`, { params: { n } }).then((r) => r.data);
}

export function uploadManual(campId: number, file: File) {
  const form = new FormData();
  form.append('file', file);
  return http
    .post(`/manuals/${campId}/upload`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    .then((r) => r.data);
}

export function pasteManual(campId: number, payload: PasteIn) {
  return http.post(`/manuals/${campId}/paste`, payload).then((r) => r.data);
}

export function deleteManual(campId: number) {
  return http.delete(`/manuals/${campId}`).then((r) => r.data);
}