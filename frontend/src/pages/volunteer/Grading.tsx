import { useEffect, useMemo, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import {
  Button,
  Card,
  Collapse,
  Empty,
  Input,
  Modal,
  Skeleton,
  Space,
  Spin,
  Tag,
  Timeline,
  Typography,
  App as AntdApp,
} from 'antd';
import {
  CheckCircleOutlined,
  ReloadOutlined,
  SaveOutlined,
  FileTextOutlined,
  StarFilled,
  ThunderboltOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';

import {
  useConfirmGrade,
  useGenerateGrade,
  useGradeDraft,
  usePendingGrades,
  useRegenerateGrade,
  volunteerKeys,
} from '@/hooks/useVolunteer';
import { useQueryClient } from '@tanstack/react-query';
import StarPicker from '@/components/StarPicker';
import StatusTag from '@/components/Tag';
import type { PendingGradeOut, StudentArchive } from '@/api/types';
import { http } from '@/api/client';

const { TextArea } = Input;
const { Text, Title } = Typography;

/**
 * P7 志愿者·作业评改（volunteer-grade）
 *
 * 页面结构（grid 280px + 主区）：
 *  - 页头：标题"作业评改" + 志愿者徽章 + "X人待评改" badge + "批量确认"按钮
 *  - 左栏：待评改列表（usePendingGrades），选中项高亮
 *  - 右栏：选中后展示评改详情：
 *      1. 学员信息头（昵称·Day N·提交日期 + 查看完整档案链接）
 *      2. 学员本次打卡内容（readOnly Card）
 *      3. 历史档案参考区（Collapse，默认展开，时间线）
 *      4. AI 评改结果 Card（星级 / 评语 / 维度依据 / 评分标准折叠）
 *      5. 操作按钮：确认并同步 / 仅保存不同步 / 重新生成
 *
 * 交互：
 *  - 进入页面或点击待评改项 → 自动调 useGenerateGrade(checkinId) 加载 AI 评改
 *  - 星级/评语可编辑后点击"确认并同步" → useConfirmGrade
 *  - "重新生成" → useRegenerateGrade
 *  - 当前 checkinId 同时支持 local state + URL ?checkin= 同步
 */

// 维度名（中文），用于在 dimension_scores 中取 name
const DIMENSION_LABELS: Record<string, string> = {
  completeness: '完整度',
  authenticity: '行动真实性',
  depth: '收获深度',
  progress: '进步性',
  originality: '原创性',
};

export default function VolunteerGrading() {
  const params = useParams<{ id: string }>();
  const campId = Number(params.id);
  const [searchParams, setSearchParams] = useSearchParams();
  const { message } = AntdApp.useApp();
  const qc = useQueryClient();

  // ---------- URL ?checkin= 同步 ----------
  const urlCheckinId = useMemo(() => {
    const v = searchParams.get('checkin');
    return v ? Number(v) : undefined;
  }, [searchParams]);

  // 当前选中的 checkinId（URL 优先，便于刷新保留）
  const [selectedCheckinId, setSelectedCheckinId] = useState<number | undefined>(
    urlCheckinId
  );

  // URL 变化 → 同步本地
  useEffect(() => {
    if (urlCheckinId && urlCheckinId !== selectedCheckinId) {
      setSelectedCheckinId(urlCheckinId);
    }
  }, [urlCheckinId, selectedCheckinId]);

  // ---------- 数据 ----------
  const { data: pending, isLoading: pendingLoading } = usePendingGrades(
    Number.isFinite(campId) ? campId : undefined
  );
  const generateMutation = useGenerateGrade();
  const regenerateMutation = useRegenerateGrade();
  const confirmMutation = useConfirmGrade(campId);

  // 当前选中的待评改项
  const currentItem = useMemo<PendingGradeOut | undefined>(() => {
    if (!selectedCheckinId || !pending) return undefined;
    return pending.find((p: PendingGradeOut) => p.checkin_id === selectedCheckinId);
  }, [selectedCheckinId, pending]);

  // 评改草稿（来自 cache）
  const draft = useGradeDraft(selectedCheckinId);

  // 受控星级 / 评语（草稿变化时同步初值）
  const [stars, setStars] = useState<number | undefined>(undefined);
  const [comment, setComment] = useState<string>('');
  useEffect(() => {
    if (draft) {
      setStars(draft.stars);
      setComment(draft.comment ?? '');
    } else {
      setStars(undefined);
      setComment('');
    }
  }, [draft]);

  // ---------- 自动生成：选中或进入页面时 ----------
  // 列表加载完成后，若 URL 已有 checkin 或没有选中项，自动选中第一个
  useEffect(() => {
    if (!pending || pending.length === 0) return;
    if (selectedCheckinId && pending.some((p: PendingGradeOut) => p.checkin_id === selectedCheckinId)) return;
    const first = pending[0].checkin_id;
    setSelectedCheckinId(first);
    setSearchParams({ checkin: String(first) }, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending]);

  // 选中项变化 → 触发 AI 生成（若 cache 中无草稿）
  useEffect(() => {
    if (!selectedCheckinId) return;
    // 已存在草稿不再请求（直接从 queryClient cache 读取，避免在 effect 内调用 hook）
    const existing = qc.getQueryData<import('@/api/types').GradeDraftOut>(
      volunteerKeys.gradeDraft(selectedCheckinId)
    );
    if (existing) return;
    generateMutation.mutate(selectedCheckinId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCheckinId]);

  // ---------- 操作 ----------
  const handleSelect = (checkinId: number) => {
    if (checkinId === selectedCheckinId) return;
    setSelectedCheckinId(checkinId);
    setSearchParams({ checkin: String(checkinId) });
  };

  const handleRegenerate = () => {
    if (!selectedCheckinId) return;
    regenerateMutation.mutate(selectedCheckinId, {
      onSuccess: () => {
        message.success('已重新生成评改');
      },
    });
  };

  const handleConfirm = (sync: boolean) => {
    if (!selectedCheckinId) return;
    if (!stars) {
      message.warning('请选择星级（1-3）');
      return;
    }
    if (sync) {
      // 确认并同步：调 useConfirmGrade
      confirmMutation.mutate(
        { checkin_id: selectedCheckinId, stars, comment },
        {
          onSuccess: (res) => {
            if (res.success) {
              message.success(`已确认并同步到破局（${res.message}）`);
            } else {
              message.warning(`已保存：${res.message}`);
            }
          },
        }
      );
    } else {
      // 仅保存不同步：MVP 用本地状态 + toast 提示（后端暂无独立"保存草稿"接口）
      // 通过 confirm 接口降级：实际也调用 confirm，但不期望同步成功
      Modal.confirm({
        title: '仅保存不同步',
        content:
          'MVP 暂未提供"仅保存"接口，确认后会尝试同步到破局；如需降级请在接口配置页关闭 Token。是否继续？',
        okText: '继续调用接口',
        cancelText: '取消',
        onOk: () => {
          confirmMutation.mutate(
            { checkin_id: selectedCheckinId, stars, comment },
            {
              onSuccess: (res) => {
                message.info(res.success ? '已同步' : `已尝试保存：${res.message}`);
              },
            }
          );
        },
      });
    }
  };

  // ---------- 渲染 ----------
  const pendingCount = pending?.length ?? 0;
  const generating = generateMutation.isPending || regenerateMutation.isPending;

  return (
    <div style={{ padding: 24 }}>
      {/* 页头 */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 20,
          gap: 12,
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Title level={3} style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>
              作业评改
            </Title>
            <Tag
              style={{
                background: 'var(--volunteer-bg)',
                color: 'var(--volunteer-fg)',
                border: 'none',
                borderRadius: 10,
                padding: '2px 10px',
                fontSize: 11,
                margin: 0,
              }}
            >
              志愿者
            </Tag>
          </div>
          <Text style={{ color: 'var(--text-sub)', fontSize: 13 }}>
            AI 结合手册 + 学员档案生成评改建议，确认后同步破局
          </Text>
        </div>
        <Space size={8}>
          <Tag
            style={{
              background: pendingCount > 0 ? 'var(--warning)' : 'var(--bg)',
              color: pendingCount > 0 ? '#fff' : 'var(--text-sub)',
              border: 'none',
              borderRadius: 10,
              padding: '2px 10px',
              fontSize: 12,
              fontWeight: 600,
            }}
          >
            {pendingCount} 人待评改
          </Tag>
          <Button
            size="middle"
            style={{ borderRadius: 6 }}
            onClick={() => message.info('批量确认：MVP 暂未实现，请逐条评改')}
          >
            批量确认
          </Button>
        </Space>
      </div>

      {/* 左右两栏 */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '280px 1fr',
          gap: 16,
          alignItems: 'start',
        }}
      >
        {/* 左：待评改列表 */}
        <Card
          bordered={false}
          style={{ borderRadius: 10, position: 'sticky', top: 16 }}
          bodyStyle={{ padding: 14 }}
          title={<span style={{ fontSize: 14, fontWeight: 600 }}>待评改列表</span>}
        >
          {pendingLoading ? (
            <Skeleton active paragraph={{ rows: 4 }} />
          ) : !pending || pending.length === 0 ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="暂无待评改作业"
              style={{ padding: '20px 0' }}
            />
          ) : (
            <div style={{ maxHeight: 'calc(100vh - 240px)', overflowY: 'auto' }}>
              {pending.map((item: PendingGradeOut) => (
                <PendingItem
                  key={item.checkin_id}
                  item={item}
                  selected={item.checkin_id === selectedCheckinId}
                  onClick={() => handleSelect(item.checkin_id)}
                />
              ))}
            </div>
          )}
        </Card>

        {/* 右：评改详情 */}
        <div>
          {!currentItem ? (
            <Card
              bordered={false}
              style={{ borderRadius: 10 }}
              bodyStyle={{ padding: 60 }}
            >
              <Empty
                description="请在左侧选择一名待评改学员"
                style={{ color: 'var(--text-sub)' }}
              />
            </Card>
          ) : (
            <GradingDetail
              item={currentItem}
              campId={campId}
              stars={stars}
              comment={comment}
              onStarsChange={setStars}
              onCommentChange={setComment}
              draft={draft}
              generating={generating}
              onRegenerate={handleRegenerate}
              onConfirm={handleConfirm}
              confirming={confirmMutation.isPending}
            />
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 子组件：待评改列表项
// ---------------------------------------------------------------------------
function PendingItem({
  item,
  selected,
  onClick,
}: {
  item: PendingGradeOut;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <div
      onClick={onClick}
      style={{
        padding: '10px 12px',
        borderRadius: 6,
        marginBottom: 6,
        cursor: 'pointer',
        background: selected ? 'var(--primary-light)' : 'transparent',
        border: selected ? '1px solid var(--primary)' : '1px solid transparent',
        transition: 'background 0.15s, border-color 0.15s',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <strong
          style={{
            fontSize: 13,
            color: selected ? 'var(--primary)' : 'var(--text)',
          }}
        >
          {item.student_nickname}
        </strong>
        <span style={{ color: 'var(--text-light)', fontSize: 12 }}>Day{item.day_number}</span>
      </div>
      <div style={{ color: 'var(--text-light)', fontSize: 12, marginTop: 4 }}>
        {dayjs(item.checkin_date).format('MM/DD')} · 提交待评改
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 子组件：评改详情
// ---------------------------------------------------------------------------
function GradingDetail({
  item,
  campId,
  stars,
  comment,
  onStarsChange,
  onCommentChange,
  draft,
  generating,
  onRegenerate,
  onConfirm,
  confirming,
}: {
  item: PendingGradeOut;
  campId: number;
  stars: number | undefined;
  comment: string;
  onStarsChange: (v: number | undefined) => void;
  onCommentChange: (v: string) => void;
  draft: import('@/api/types').GradeDraftOut | undefined;
  generating: boolean;
  onRegenerate: () => void;
  onConfirm: (sync: boolean) => void;
  confirming: boolean;
}) {
  // 学员档案：用于"历史档案参考"
  const [archive, setArchive] = useState<StudentArchive | null>(null);
  const [archiveLoading, setArchiveLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (!item.student_id) return;
    setArchiveLoading(true);
    http
      .get<StudentArchive>(`/students/${item.student_id}`)
      .then((r) => r.data)
      .then((data) => {
        if (!cancelled) setArchive(data);
      })
      .catch(() => {
        if (!cancelled) setArchive(null);
      })
      .finally(() => {
        if (!cancelled) setArchiveLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [item.student_id]);

  // 提取引用行：从 content 中解析"今日行动：xxx"
  const contentPreview = useMemo(() => {
    if (!item.content) return '';
    return item.content;
  }, [item.content]);

  // 维度得分依据
  const dimensions: Array<{ key: string; name: string; score: string }> = useMemo(() => {
    const list = (draft?.dimension_scores ?? []) as Array<Record<string, unknown>>;
    if (list.length === 0) {
      // 兜底：显示 5 个默认维度（无评分时仅展示名）
      return Object.keys(DIMENSION_LABELS).map((k) => ({
        key: k,
        name: DIMENSION_LABELS[k],
        score: '—',
      }));
    }
    return list.map((d, idx) => {
      const key = String(d.key ?? d.name ?? `dim_${idx}`);
      const name =
        (d.name as string) ||
        DIMENSION_LABELS[key] ||
        (d.label as string) ||
        key;
      const score = (d.score as string) || (d.level as string) || (d.value as string) || '—';
      return { key, name, score };
    });
  }, [draft]);

  const isValid = (stars ?? 0) >= 2;
  const starLabel = !stars
    ? '请选择星级'
    : isValid
    ? `${stars}星 · 有效打卡`
    : `${stars}星 · 无效打卡`;

  return (
    <>
      {/* 1. 学员信息头 */}
      <Card
        bordered={false}
        style={{ borderRadius: 10, marginBottom: 12 }}
        bodyStyle={{ padding: 18 }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'space-between',
            gap: 12,
          }}
        >
          <div>
            <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text)' }}>
              {item.student_nickname} · Day{item.day_number} 打卡
            </div>
            <div style={{ color: 'var(--text-sub)', fontSize: 13, marginTop: 4 }}>
              {item.submitted_at
                ? `${dayjs(item.submitted_at).format('MM/DD HH:mm')} 提交`
                : `${dayjs(item.checkin_date).format('MM/DD')} 提交`}
            </div>
          </div>
          <Link to={`/camp/${campId}/volunteer/archive/${item.student_id}`}>
            <Button size="small" icon={<FileTextOutlined />} style={{ borderRadius: 6 }}>
              查看完整档案
            </Button>
          </Link>
        </div>

        <div
          style={{
            background: 'var(--bg)',
            borderRadius: 6,
            padding: '12px 14px',
            fontSize: 13,
            color: 'var(--text)',
            lineHeight: 1.7,
            whiteSpace: 'pre-wrap',
            marginTop: 14,
            maxHeight: 200,
            overflowY: 'auto',
          }}
        >
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6, color: 'var(--text)' }}>
            学员本次打卡内容：
          </div>
          {contentPreview || (
            <span style={{ color: 'var(--text-light)' }}>（无内容）</span>
          )}
        </div>
      </Card>

      {/* 2. 历史档案参考（默认展开） */}
      <Card
        bordered={false}
        style={{ borderRadius: 10, marginBottom: 12 }}
        bodyStyle={{ padding: 18 }}
        title={
          <span style={{ fontSize: 14, fontWeight: 600 }}>
            该学员历史档案参考（判断进步/原创性）
          </span>
        }
      >
        <Collapse
          defaultActiveKey={['archive']}
          ghost
          items={[
            {
              key: 'archive',
              label: (
                <span style={{ fontSize: 13, color: 'var(--text-sub)' }}>
                  AI 评改时会参考以下历史作业，判断是否抄袭/重复、是否有进步
                </span>
              ),
              children: <ArchiveTimeline loading={archiveLoading} archive={archive} />,
            },
          ]}
        />
      </Card>

      {/* 3. AI 评改结果 */}
      <Card
        bordered={false}
        style={{ borderRadius: 10 }}
        bodyStyle={{ padding: 18 }}
        title={
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <span style={{ fontSize: 14, fontWeight: 600 }}>
              <ThunderboltOutlined style={{ color: 'var(--primary)', marginRight: 6 }} />
              AI 评改结果
            </span>
            {generating ? (
              <StatusTag status="pending" text="生成中" />
            ) : draft ? (
              <StatusTag status="valid" text="已生成 · 可修改" />
            ) : (
              <StatusTag status="warn" text="待生成" />
            )}
          </div>
        }
      >
        {generating && !draft ? (
          <div style={{ padding: '40px 0', textAlign: 'center' }}>
            <Spin tip="AI 正在生成评改…" />
          </div>
        ) : !draft ? (
          <Empty
            description="尚未生成评改，点击下方「重新生成」按钮触发 AI"
            style={{ padding: '20px 0' }}
          />
        ) : (
          <>
            {/* 星级 */}
            <div style={{ marginBottom: 16 }}>
              <div
                style={{
                  fontSize: 13,
                  fontWeight: 600,
                  color: 'var(--text)',
                  marginBottom: 8,
                }}
              >
                星级
              </div>
              <Space size={12} align="center">
                <StarPicker value={stars} onChange={onStarsChange} />
                <span
                  style={{
                    fontSize: 13,
                    color: stars ? (isValid ? 'var(--success)' : 'var(--danger)') : 'var(--text-sub)',
                    fontWeight: 600,
                  }}
                >
                  {starLabel}
                </span>
              </Space>
            </div>

            {/* 评语 */}
            <div style={{ marginBottom: 16 }}>
              <div
                style={{
                  fontSize: 13,
                  fontWeight: 600,
                  color: 'var(--text)',
                  marginBottom: 8,
                }}
              >
                评语
              </div>
              <TextArea
                value={comment}
                onChange={(e) => onCommentChange(e.target.value)}
                rows={5}
                placeholder="AI 评语会预填于此，可编辑修改"
                style={{ borderRadius: 6 }}
              />
            </div>

            {/* 维度得分依据 */}
            <div style={{ marginBottom: 16 }}>
              <div
                style={{
                  fontSize: 13,
                  fontWeight: 600,
                  color: 'var(--text)',
                  marginBottom: 8,
                }}
              >
                评改依据（维度得分）
              </div>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))',
                  gap: 8,
                }}
              >
                {dimensions.map((d) => (
                  <div
                    key={d.key}
                    style={{
                      background: 'var(--bg)',
                      border: '1px solid var(--border)',
                      borderRadius: 6,
                      padding: '8px 10px',
                      fontSize: 13,
                      color: 'var(--text)',
                    }}
                  >
                    {d.name}：
                    <strong style={{ color: 'var(--primary)' }}>{d.score}</strong>
                  </div>
                ))}
              </div>
            </div>

            {/* 评分标准参考（折叠） */}
            <Collapse
              ghost
              items={[
                {
                  key: 'scoring',
                  label: (
                    <span style={{ fontSize: 13, color: 'var(--text-sub)' }}>
                      查看评分标准参考
                    </span>
                  ),
                  children: (
                    <div
                      style={{
                        background: 'var(--bg)',
                        borderRadius: 6,
                        padding: '10px 12px',
                        fontSize: 13,
                        color: 'var(--text)',
                        lineHeight: 1.7,
                      }}
                    >
                      <div>
                        <strong style={{ color: 'var(--star)' }}>三星：</strong>
                        各维度达标 + 有进步亮点
                      </div>
                      <div>
                        <strong style={{ color: 'var(--star)' }}>二星：</strong>
                        基本达标 + 完整真实无抄袭
                      </div>
                      <div>
                        <strong style={{ color: 'var(--star)' }}>一星：</strong>
                        敷衍 / 不完整 / 套话 / 抄袭重复
                      </div>
                      <div style={{ color: 'var(--text-sub)', marginTop: 6, fontSize: 12 }}>
                        注：有效打卡 = ≥2 星。具体配置请到「评分标准」调整。
                      </div>
                    </div>
                  ),
                },
              ]}
            />

            <div
              style={{
                height: 1,
                background: 'var(--border)',
                margin: '12px 0',
              }}
            />

            {/* 操作按钮 */}
            <Space wrap>
              <Button
                type="primary"
                icon={<CheckCircleOutlined />}
                loading={confirming}
                onClick={() => onConfirm(true)}
                style={{ borderRadius: 6 }}
              >
                确认并同步
              </Button>
              <Button
                icon={<SaveOutlined />}
                loading={confirming}
                onClick={() => onConfirm(false)}
                style={{ borderRadius: 6 }}
              >
                仅保存不同步
              </Button>
              <Button
                icon={<ReloadOutlined />}
                loading={generating}
                onClick={onRegenerate}
                style={{ borderRadius: 6 }}
              >
                重新生成
              </Button>
            </Space>
            <div style={{ fontSize: 12, color: 'var(--text-sub)', marginTop: 8 }}>
              确认后将调用破局「给学员作业打分和评价」接口同步星级与评语，并写入该学员档案。
            </div>
          </>
        )}
      </Card>
    </>
  );
}

// ---------------------------------------------------------------------------
// 子组件：历史档案时间线
// ---------------------------------------------------------------------------
function ArchiveTimeline({
  loading,
  archive,
}: {
  loading: boolean;
  archive: StudentArchive | null;
}) {
  if (loading) {
    return (
      <div style={{ padding: '20px 0' }}>
        <Skeleton active paragraph={{ rows: 3 }} />
      </div>
    );
  }
  if (!archive || archive.timeline.length === 0) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description="暂无历史打卡记录"
        style={{ padding: '12px 0' }}
      />
    );
  }
  // 取最近 5-10 条
  const recent = archive.timeline.slice(0, 10);

  return (
    <Timeline
      style={{ marginTop: 8 }}
      items={recent.map((item) => {
        const isPending = item.grade_status === 'pending';
        const isInvalid = item.is_valid === false;
        const color = isPending
          ? 'var(--warning)'
          : isInvalid
          ? 'var(--danger)'
          : 'var(--primary)';
        return {
          color,
          dot: isPending ? (
            <span style={{ color }}>●</span>
          ) : (
            <StarFilled style={{ color, fontSize: 12 }} />
          ),
          children: (
            <div>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  fontSize: 13,
                  fontWeight: 600,
                  color: 'var(--text)',
                }}
              >
                <span>
                  Day{item.day_number} · {dayjs(item.checkin_date).format('MM/DD')}
                </span>
                {item.stars != null ? (
                  <span style={{ color: 'var(--star)', letterSpacing: 1, fontSize: 12 }}>
                    {Array.from({ length: 3 }).map((_, i) => (
                      <span key={i} style={{ opacity: i < (item.stars ?? 0) ? 1 : 0.25 }}>
                        ★
                      </span>
                    ))}
                  </span>
                ) : (
                  <StatusTag status="pending" text="待评改" />
                )}
                {item.stars != null && !item.is_valid && (
                  <StatusTag status="invalid" text="无效" />
                )}
              </div>
              {item.content && (
                <div
                  style={{
                    color: 'var(--text-sub)',
                    fontSize: 13,
                    marginTop: 4,
                    lineHeight: 1.6,
                    background: isInvalid ? '#fef2f2' : 'var(--bg)',
                    padding: isInvalid ? '6px 10px' : 0,
                    borderRadius: 6,
                  }}
                >
                  {truncate(item.content, 140)}
                </div>
              )}
            </div>
          ),
        };
      })}
    />
  );
}

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------
function truncate(s: string, n: number) {
  return s.length > n ? `${s.slice(0, n)}…` : s;
}
