import { useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Empty,
  Input,
  Modal,
  Popconfirm,
  Spin,
  Tabs,
  Upload,
  message,
} from 'antd';
import type { UploadProps } from 'antd';
import {
  ArrowLeftOutlined,
  CloudUploadOutlined,
  DeleteOutlined,
  EyeOutlined,
  FileTextOutlined,
  InboxOutlined,
  SaveOutlined,
} from '@ant-design/icons';
import { Link, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as manualApi from '@/api/manual';
import { toastOnBizError } from '@/api/client';
import { useCamp } from '@/hooks/useCamps';
import type { ManualWithPreview } from '@/api/types';

/**
 * P9 手册管理（design.md 第六章 P9）
 *
 * 功能：
 * - 黄色提示条：飞书手册经破局自定义域名封装，无法导出/复制。请自行通过 OCR 等方式得到文本后上传。
 * - 当前手册卡：文件名 / 上传时间 / 字数 / 章节数 + 预览 / 删除按钮。
 * - 上传区：Tab 切换"上传文件 / 粘贴文本"；Upload.Dragger + 粘贴 TextArea + 保存按钮。
 * - 手册预览卡：前 500 字展示（接口已包含预览字段）。
 *
 * 数据流：
 * - useManual(campId)         加载当前手册（meta + preview）
 * - useUploadManual           上传文件
 * - useSavePaste              粘贴文本
 * - useDeleteManual           删除
 *
 * 替换后提示"建议在「学习路线」点击重新规划"。
 */

// 统一 queryKey，便于 invalidate
export const manualKeys = {
  detail: (campId: number) => ['manual', campId] as const,
};

/** 获取手册元信息 + 前 500 字预览 */
export function useManual(campId?: number) {
  return useQuery({
    queryKey: manualKeys.detail(campId ?? -1),
    queryFn: () => manualApi.getManual(campId as number, 500),
    enabled: !!campId,
    // 404（无手册）视作"无手册"空态，不报错
    retry: (failureCount, error: unknown) => {
      const code = (error as { code?: number })?.code;
      if (code === 1002) return false; // NOT_FOUND
      return failureCount < 1;
    },
  });
}

/** 上传文件 */
export function useUploadManual(campId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => manualApi.uploadManual(campId, file),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: manualKeys.detail(campId) });
      qc.invalidateQueries({ queryKey: ['camp', campId] });
      message.success('手册上传成功');
    },
    onError: (err) => {
      toastOnBizError(err);
    },
  });
}

/** 粘贴文本 */
export function useSavePaste(campId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (content: string) => manualApi.pasteManual(campId, { content }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: manualKeys.detail(campId) });
      qc.invalidateQueries({ queryKey: ['camp', campId] });
      message.success('手册文本保存成功');
    },
    onError: (err) => {
      toastOnBizError(err);
    },
  });
}

/** 删除手册 */
export function useDeleteManual(campId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => manualApi.deleteManual(campId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: manualKeys.detail(campId) });
      qc.invalidateQueries({ queryKey: ['camp', campId] });
      message.success('手册已删除');
    },
    onError: (err) => {
      toastOnBizError(err);
    },
  });
}

// ---------------------------------------------------------------------------
// 组件
// ---------------------------------------------------------------------------

export default function Manual() {
  const params = useParams();
  const campId = Number(params.id);
  const { data: camp } = useCamp(Number.isFinite(campId) ? campId : undefined);
  const { data, isLoading, error } = useManual(Number.isFinite(campId) ? campId : undefined);
  const uploadMut = useUploadManual(campId);
  const pasteMut = useSavePaste(campId);
  const deleteMut = useDeleteManual(campId);

  // 404 表示无手册：作为空态而非错误态
  const isNotFound = (error as { code?: number } | null)?.code === 1002;

  return (
    <div style={{ padding: 24, maxWidth: 960, margin: '0 auto' }}>
      {/* 页头 */}
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          marginBottom: 16,
        }}
      >
        <div>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>手册管理</h2>
          <div style={{ color: 'var(--text-sub)', fontSize: 13, marginTop: 4 }}>
            手册文本作为 AI 规划路线 / 生成打卡 / 评改作业的参考上下文
            {camp ? ` · ${camp.name}` : ''}
          </div>
        </div>
        <Link to={`/camp/${campId}/student`}>
          <Button icon={<ArrowLeftOutlined />}>返回</Button>
        </Link>
      </div>

      {/* 黄色提示条 */}
      <Alert
        type="warning"
        showIcon
        style={{ marginBottom: 16, borderRadius: 10 }}
        message="飞书手册经破局自定义域名封装，无法导出/复制。请自行通过 OCR 等方式得到文本后上传，与主流程解耦。"
      />

      {/* 当前手册卡 */}
      <Card
        title="当前手册"
        style={{ marginBottom: 16, borderRadius: 10 }}
        bodyStyle={{ padding: 16 }}
        loading={isLoading}
      >
        {!isLoading && (isNotFound || !data?.manual) ? (
          <Empty
            image={<FileTextOutlined style={{ fontSize: 36, color: 'var(--text-light)' }} />}
            description="尚未配置手册"
          />
        ) : data?.manual ? (
          <CurrentManualCard
            data={data}
            onPreview={() => openPreview(data)}
            onDelete={() => deleteMut.mutate()}
            deleting={deleteMut.isPending}
          />
        ) : null}
      </Card>

      {/* 上传 / 替换 */}
      <Card
        title="上传 / 替换手册"
        style={{ marginBottom: 16, borderRadius: 10 }}
        bodyStyle={{ padding: 16 }}
      >
        <ManualUploadPanel
          uploading={uploadMut.isPending}
          pasting={pasteMut.isPending}
          onUpload={(file) => uploadMut.mutateAsync(file)}
          onPaste={(text) => pasteMut.mutateAsync(text)}
        />
        <div
          style={{
            marginTop: 12,
            fontSize: 12,
            color: 'var(--text-sub)',
            lineHeight: 1.7,
          }}
        >
          行动营期间手册可能更新，可随时替换。
          <span style={{ color: 'var(--warning)' }}>
            替换后建议在「学习路线」点击重新规划。
          </span>
        </div>
      </Card>

      {/* 手册预览（前 500 字） */}
      <Card title="手册预览（前 500 字）" style={{ borderRadius: 10 }} bodyStyle={{ padding: 16 }}>
        {isLoading ? (
          <div style={{ textAlign: 'center', padding: 24 }}>
            <Spin />
          </div>
        ) : isNotFound || !data?.preview ? (
          <Empty description="暂无手册预览" />
        ) : (
          <PreviewBox text={data.preview.preview} />
        )}
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 子组件
// ---------------------------------------------------------------------------

function CurrentManualCard({
  data,
  onPreview,
  onDelete,
  deleting,
}: {
  data: ManualWithPreview;
  onPreview: () => void;
  onDelete: () => void;
  deleting: boolean;
}) {
  const { manual, preview } = data;

  // 上传时间：uploaded_at / updated_at 兜底
  const uploadedAt = useMemo(() => {
    const ts = manual.uploaded_at ?? manual.updated_at ?? manual.created_at;
    if (!ts) return '-';
    // ISO 字符串 -> YYYY/MM/DD HH:mm
    const d = new Date(ts);
    if (Number.isNaN(d.getTime())) return ts;
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${d.getFullYear()}/${pad(d.getMonth() + 1)}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }, [manual.uploaded_at, manual.updated_at, manual.created_at]);

  const wordCount = manual.word_count ?? preview.word_count ?? 0;

  // 章节数：根据"## "段落粗略估算（仅展示用）
  const chapterCount = useMemo(() => {
    const text = manual.content ?? preview.preview ?? '';
    const matches = text.match(/^\s*#{1,6}\s+/gm);
    return matches?.length ?? 0;
  }, [manual.content, preview.preview]);

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 16,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0 }}>
        <div
          style={{
            fontSize: 28,
            width: 48,
            height: 48,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'var(--primary-light)',
            borderRadius: 10,
            color: 'var(--primary)',
            flexShrink: 0,
          }}
        >
          <FileTextOutlined />
        </div>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontWeight: 600, fontSize: 14 }} title={manual.filename ?? ''}>
            {manual.filename ?? '未命名手册'}
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-sub)', marginTop: 6 }}>
            上传于 {uploadedAt} · 约 {wordCount.toLocaleString()} 字
            {chapterCount > 0 ? ` · 含 ${chapterCount} 章节` : ''}
          </div>
        </div>
      </div>
      <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
        <Button icon={<EyeOutlined />} onClick={onPreview}>
          预览
        </Button>
        <Popconfirm
          title="确认删除手册？"
          description="删除后 AI 相关功能将降级，路线生成也会受影响。"
          okText="删除"
          okButtonProps={{ danger: true }}
          cancelText="取消"
          onConfirm={onDelete}
        >
          <Button danger icon={<DeleteOutlined />} loading={deleting}>
            删除
          </Button>
        </Popconfirm>
      </div>
    </div>
  );
}

function ManualUploadPanel({
  uploading,
  pasting,
  onUpload,
  onPaste,
}: {
  uploading: boolean;
  pasting: boolean;
  onUpload: (file: File) => Promise<unknown>;
  onPaste: (text: string) => Promise<unknown>;
}) {
  const [pasteText, setPasteText] = useState('');

  const draggerProps: UploadProps = {
    multiple: false,
    accept: '.md,.txt,.markdown,text/markdown,text/plain',
    showUploadList: false,
    beforeUpload: async (file) => {
      // 限大小 5MB（手册通常较小）
      if (file.size > 5 * 1024 * 1024) {
        message.error('文件过大，请控制在 5MB 以内');
        return Upload.LIST_IGNORE;
      }
      try {
        await onUpload(file);
      } catch {
        // onError 已 toast
      }
      return Upload.LIST_IGNORE; // 阻止 antd 自动上传
    },
  };

  const handleSavePaste = async () => {
    const content = pasteText.trim();
    if (!content) {
      message.warning('请先粘贴手册文本');
      return;
    }
    try {
      await onPaste(content);
      setPasteText('');
    } catch {
      // onError 已 toast
    }
  };

  return (
    <Tabs
      defaultActiveKey="file"
      items={[
        {
          key: 'file',
          label: (
            <span>
              <CloudUploadOutlined /> 上传文件
            </span>
          ),
          children: (
            <Upload.Dragger {...draggerProps} disabled={uploading}>
              <div style={{ padding: '12px 0' }}>
                <p style={{ margin: 0, fontSize: 32, color: 'var(--primary)' }}>
                  <InboxOutlined />
                </p>
                <p style={{ margin: '8px 0 0', fontSize: 14, color: 'var(--text)' }}>
                  点击或拖拽上传手册文本
                </p>
                <p style={{ margin: '4px 0 0', fontSize: 12, color: 'var(--text-light)' }}>
                  支持 .md / .txt 格式，单文件 ≤ 5MB
                </p>
              </div>
            </Upload.Dragger>
          ),
        },
        {
          key: 'paste',
          label: '粘贴文本',
          children: (
            <div>
              <Input.TextArea
                value={pasteText}
                onChange={(e) => setPasteText(e.target.value)}
                placeholder="将手册文本粘贴至此……"
                autoSize={{ minRows: 6, maxRows: 16 }}
                style={{ borderRadius: 6 }}
                disabled={pasting}
              />
              <div style={{ marginTop: 12, textAlign: 'right' }}>
                <Button
                  type="primary"
                  icon={<SaveOutlined />}
                  loading={pasting}
                  onClick={handleSavePaste}
                >
                  保存为手册
                </Button>
              </div>
            </div>
          ),
        },
      ]}
    />
  );
}

function PreviewBox({ text }: { text: string }) {
  return (
    <pre
      style={{
        margin: 0,
        padding: 16,
        background: 'var(--bg)',
        border: '1px solid var(--border)',
        borderRadius: 6,
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
        lineHeight: 1.7,
        fontSize: 13,
        color: 'var(--text)',
        maxHeight: 480,
        overflow: 'auto',
        fontFamily:
          'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "PingFang SC", monospace',
      }}
    >
      {text}
    </pre>
  );
}

// 预览弹窗（不持久化在组件内，提到模块级函数以便测试）
function openPreview(data: ManualWithPreview) {
  const full = data.manual.content ?? data.preview.preview;
  const filename = data.manual.filename ?? '手册预览';
  Modal.info({
    title: `预览 · ${filename}`,
    icon: <EyeOutlined style={{ color: 'var(--primary)' }} />,
    width: 720,
    content: (
      <pre
        style={{
          margin: 0,
          padding: 16,
          background: 'var(--bg)',
          border: '1px solid var(--border)',
          borderRadius: 6,
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          lineHeight: 1.7,
          fontSize: 13,
          maxHeight: '60vh',
          overflow: 'auto',
        }}
      >
        {full || '暂无内容'}
      </pre>
    ),
    okText: '关闭',
  });
}