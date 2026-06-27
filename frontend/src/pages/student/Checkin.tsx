import { useEffect, useMemo, useState } from 'react';
import {
  Button,
  Card,
  Col,
  Form,
  Input,
  Row,
  Space,
  Spin,
  Switch,
  Table,
  Tag,
  Typography,
  Upload,
  App as AntdApp,
  Empty,
} from 'antd';
import type { UploadProps } from 'antd';
import {
  CloudUploadOutlined,
  CopyOutlined,
  CheckOutlined,
  EditOutlined,
  ReloadOutlined,
  ThunderboltFilled,
} from '@ant-design/icons';
import { useParams } from 'react-router-dom';
import dayjs from 'dayjs';

import { useCamp } from '@/hooks/useCamps';
import {
  useCheckins,
  useGenerateCheckin,
  useSubmitCheckin,
  useTodayTasks,
} from '@/hooks/useStudent';
import StatusTag, { type StatusKey } from '@/components/Tag';
import type {
  CheckinDraftOut,
  CheckinRecordOut,
  GradeStatus,
} from '@/api/types';

const { TextArea } = Input;
const { Text, Title } = Typography;

/**
 * P5 学员·打卡生成（student-checkin）
 *
 * 页面结构（对齐 design.md P5 + ui-prototype/index.html P: STUDENT-CHECKIN）：
 *  - 页头：标题"打卡生成" + 学员徽章 + Day N
 *  - 左右两栏：
 *      左：今日所做输入（文字+图片）+ 提交方式 Switch + ✨ 生成打卡内容
 *      右：四板块卡片（今日行动/今日收获/好事分享/下一步行动）+ 状态徽章 + 提交/编辑/重新生成按钮
 *  - 底部：本期打卡记录表（日期/Day/核心行动/星级/状态）
 *
 * 交互逻辑：
 *  - 生成中：useGenerateCheckin.isPending → 四卡片显示骨架 + 状态徽章"生成中"
 *  - 手动提交：拼接四板块内容 → navigator.clipboard.writeText → 调 useSubmitCheckin(auto=false)
 *  - 自动提交：直接调 useSubmitCheckin(auto=true)
 *  - Switch 联动按钮文案 + 底部提示文案
 *
 * MVP 学员身份：checkin 落库 student_id=0（后端约定），前端无需关心。
 */

// 四板块 key（统一在此定义，便于复用与翻译）
type DraftKey = keyof CheckinDraftOut;
const DRAFT_BLOCKS: Array<{ key: DraftKey; label: string }> = [
  { key: 'today_action', label: '今日行动' },
  { key: 'today_gain', label: '今日收获' },
  { key: 'good_thing', label: '好事分享' },
  { key: 'next_step', label: '下一步行动' },
];

const EMPTY_DRAFT: CheckinDraftOut = {
  today_action: '',
  today_gain: '',
  good_thing: '',
  next_step: '',
};

export default function StudentCheckin() {
  const params = useParams<{ id: string }>();
  const campId = Number(params.id);
  const { message } = AntdApp.useApp();

  // 基础数据
  const { data: camp } = useCamp(Number.isFinite(campId) ? campId : undefined);
  const { data: todayOut } = useTodayTasks(
    Number.isFinite(campId) ? campId : undefined
  );
  const { data: checkins, isLoading: checkinsLoading } = useCheckins(
    Number.isFinite(campId) ? campId : undefined
  );

  // 表单（受控，便于生成后回填 / 编辑 / 重新生成）
  const [form] = Form.useForm<{ text: string }>();
  const textValue = Form.useWatch('text', form);

  // 提交方式：手动/自动（默认手动 = false）
  const [autoSubmit, setAutoSubmit] = useState(false);

  // 生成结果（AI 产出，可编辑）
  const [draft, setDraft] = useState<CheckinDraftOut | null>(null);
  const [generating, setGenerating] = useState(false);

  // 编辑态：编辑时四卡片允许修改；非编辑态为只读
  const [editing, setEditing] = useState(false);

  // 当前 Day（优先 today 接口；否则从 camp.current_day）
  const currentDay = useMemo(() => {
    if (todayOut?.day_number != null) return todayOut.day_number;
    if (camp?.current_day != null) return camp.current_day;
    return null;
  }, [todayOut, camp]);

  // ---------- 图片上传（仅本地预览，不实际上传） ----------
  const [imageNames, setImageNames] = useState<string[]>([]);
  const uploadProps: UploadProps = {
    name: 'image',
    multiple: true,
    showUploadList: false,
    accept: 'image/*',
    beforeUpload: (file) => {
      // 仅展示文件名（占位提示：MVP 不实际上传图片，AI 生成基于文字）
      setImageNames((prev) => [...prev, file.name]);
      message.info(`已选择图片 ${file.name}（MVP 暂不作为生成输入）`);
      return false; // 阻止自动上传
    },
  };

  // ---------- 生成打卡内容 ----------
  const generateMutation = useGenerateCheckin(campId);
  const submitMutation = useSubmitCheckin(campId);

  // 同步 mutation pending 到本地 generating（首次进入若已有数据不算 generating）
  useEffect(() => {
    setGenerating(generateMutation.isPending);
  }, [generateMutation.isPending]);

  const handleGenerate = () => {
    const text = (textValue ?? '').trim();
    if (!text) {
      message.warning('请先填写今日所做（文字描述）');
      return;
    }
    generateMutation.mutate(
      { text },
      {
        onSuccess: (data) => {
          setDraft({ ...EMPTY_DRAFT, ...data });
          setEditing(false);
          message.success('已生成打卡内容，可编辑后提交');
        },
        // onError 已由 hook toastOnBizError 处理
      }
    );
  };

  const handleRegenerate = () => {
    // 重新生成等同于再次调用 mutation（覆盖当前 draft）
    handleGenerate();
  };

  // ---------- 提交 ----------
  const buildContent = (d: CheckinDraftOut): string => {
    return DRAFT_BLOCKS.map((b) => `${b.label}：${d[b.key]?.trim() ?? ''}`).join('\n');
  };

  const doSubmit = async (auto: boolean) => {
    if (!draft) return;
    const content = buildContent(draft);
    if (!content.trim()) {
      message.warning('打卡内容为空，请先生成或填写');
      return;
    }

    // 手动提交：先复制到剪贴板
    if (!auto) {
      try {
        if (navigator.clipboard?.writeText) {
          await navigator.clipboard.writeText(content);
        } else {
          // 兜底：textarea + execCommand（老浏览器/非 https）
          const ta = document.createElement('textarea');
          ta.value = content;
          ta.style.position = 'fixed';
          ta.style.opacity = '0';
          document.body.appendChild(ta);
          ta.select();
          document.execCommand('copy');
          document.body.removeChild(ta);
        }
        message.success('内容已复制到剪贴板，请粘贴到破局打卡页面');
      } catch (e) {
        message.warning('复制失败，请手动选择文本复制');
      }
    }

    // 落库（student_id=0 由后端约定，前端无需关心）
    submitMutation.mutate(
      { content, auto },
      {
        onSuccess: (res) => {
          if (res.submitted) {
            message.success(
              auto
                ? `已自动提交（同步状态：${syncText(res.sync_status)}）`
                : '已记录到本期打卡，等待志愿者评改'
            );
          } else {
            message.warning('提交未完成，请稍后重试');
          }
        },
      }
    );
  };

  const handleCopyOnly = async () => {
    if (!draft) {
      message.warning('暂未生成内容，无法复制');
      return;
    }
    const content = buildContent(draft);
    try {
      await navigator.clipboard.writeText(content);
      message.success('内容已复制到剪贴板');
    } catch {
      message.warning('复制失败，请手动选择文本复制');
    }
  };

  // ---------- 渲染 ----------
  const hasDraft = !!draft;
  const statusBadge = (() => {
    if (generating) return { key: 'pending' as StatusKey, text: '生成中' };
    if (hasDraft) return { key: 'valid' as StatusKey, text: '已生成' };
    return { key: 'unknown' as StatusKey, text: '待生成' };
  })();

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
              打卡生成
            </Title>
            <Tag
              style={{
                background: 'var(--student-bg)',
                color: 'var(--student-fg)',
                border: 'none',
                borderRadius: 10,
                padding: '2px 10px',
                fontSize: 11,
                margin: 0,
              }}
            >
              学员
            </Tag>
          </div>
          <Text style={{ color: 'var(--text-sub)', fontSize: 13 }}>
            输入今日所做，AI 生成结构化打卡内容
            {currentDay != null && (
              <>
                {' · '}
                <Text style={{ color: 'var(--primary)', fontWeight: 600 }}>
                  Day {currentDay}
                </Text>
              </>
            )}
          </Text>
        </div>
      </div>

      {/* 左右两栏 */}
      <Row gutter={[16, 16]}>
        {/* 左：输入 */}
        <Col xs={24} lg={12}>
          <Card
            bordered={false}
            style={{ borderRadius: 10 }}
            bodyStyle={{ padding: 18 }}
            title={
              <span style={{ fontSize: 14, fontWeight: 600 }}>今日所做（输入）</span>
            }
          >
            <Form form={form} layout="vertical">
              <Form.Item
                label="文字描述"
                required
                style={{ marginBottom: 12 }}
                tooltip="必填。AI 会基于此内容生成四板块打卡草稿。"
              >
                <Form.Item name="text" noStyle rules={[{ required: true, message: '请填写今日所做' }]}>
                  <TextArea
                    rows={5}
                    placeholder="今天做了什么？随意写，AI 会帮你整理成结构化打卡"
                    style={{ borderRadius: 6 }}
                  />
                </Form.Item>
              </Form.Item>

              <Form.Item label="图片（选填，仅作参考）" style={{ marginBottom: 12 }}>
                <Upload.Dragger
                  {...uploadProps}
                  style={{
                    background: 'var(--bg)',
                    border: '1px dashed var(--border)',
                    borderRadius: 6,
                    padding: '16px 12px',
                  }}
                >
                  <div style={{ fontSize: 22, color: 'var(--text-light)' }}>
                    <CloudUploadOutlined />
                  </div>
                  <div style={{ fontSize: 13, color: 'var(--text)', marginTop: 6 }}>
                    点击或拖拽上传图片
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-light)', marginTop: 4 }}>
                    如：改写对比截图、练习成果（MVP 不作为生成输入）
                  </div>
                </Upload.Dragger>
                {imageNames.length > 0 && (
                  <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-sub)' }}>
                    已选择 {imageNames.length} 张：
                    {imageNames.slice(-3).map((n) => (
                      <Tag key={n} style={{ marginLeft: 6 }}>
                        {n}
                      </Tag>
                    ))}
                    {imageNames.length > 3 && <Tag>…</Tag>}
                  </div>
                )}
              </Form.Item>

              <div
                style={{
                  height: 1,
                  background: 'var(--border)',
                  margin: '8px 0 16px',
                }}
              />

              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 12,
                  marginBottom: 8,
                }}
              >
                <div style={{ fontSize: 13 }}>
                  <Space size={8} align="center">
                    <Switch
                      checked={autoSubmit}
                      onChange={setAutoSubmit}
                      size="small"
                    />
                    <span>自动提交到破局</span>
                  </Space>
                  <div style={{ fontSize: 12, color: 'var(--text-sub)', marginTop: 4 }}>
                    {autoSubmit
                      ? '开启：点击下方按钮将直接调用破局接口提交'
                      : '关闭：点击下方按钮将内容复制到剪贴板，请粘贴到破局打卡页面（默认，便于把控质量）'}
                  </div>
                </div>
              </div>

              <Button
                type="primary"
                size="large"
                block
                icon={<ThunderboltFilled />}
                loading={generating}
                onClick={handleGenerate}
                style={{ borderRadius: 6 }}
              >
                生成打卡内容
              </Button>
            </Form>
          </Card>
        </Col>

        {/* 右：结果 */}
        <Col xs={24} lg={12}>
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
                <span style={{ fontSize: 14, fontWeight: 600 }}>生成结果</span>
                <StatusTag status={statusBadge.key} text={statusBadge.text} />
              </div>
            }
          >
            {generating ? (
              <div style={{ padding: '40px 0', textAlign: 'center' }}>
                <Spin tip="AI 正在生成打卡内容…" />
              </div>
            ) : !hasDraft ? (
              <Empty
                description="尚未生成内容，先在左侧填写今日所做并点击「生成打卡内容」"
                style={{ padding: '40px 0' }}
              />
            ) : (
              <DraftEditor
                draft={draft}
                editing={editing}
                onChange={(key, val) =>
                  setDraft((prev) => (prev ? { ...prev, [key]: val } : prev))
                }
              />
            )}

            {/* 底部按钮区：仅在已有草稿时显示 */}
            {hasDraft && !generating && (
              <>
                <div
                  style={{
                    background: 'var(--bg)',
                    borderRadius: 6,
                    padding: '8px 12px',
                    fontSize: 12,
                    color: 'var(--text-sub)',
                    marginTop: 16,
                  }}
                >
                  打卡内容无强制格式与字数要求，AI 依据你输入的真实情况生成，可编辑修改。
                </div>

                <Space style={{ marginTop: 16, width: '100%' }} wrap>
                  <Button
                    type="primary"
                    loading={submitMutation.isPending}
                    onClick={() => doSubmit(autoSubmit)}
                    style={{ borderRadius: 6 }}
                  >
                    {autoSubmit ? '确认并自动提交' : '复制内容 / 提交'}
                  </Button>
                  {!autoSubmit && (
                    <Button
                      icon={<CopyOutlined />}
                      onClick={handleCopyOnly}
                      style={{ borderRadius: 6 }}
                    >
                      仅复制内容
                    </Button>
                  )}
                  <Button
                    icon={editing ? <CheckOutlined /> : <EditOutlined />}
                    onClick={() => setEditing((v) => !v)}
                    style={{ borderRadius: 6 }}
                  >
                    {editing ? '完成编辑' : '编辑修改'}
                  </Button>
                  <Button
                    icon={<ReloadOutlined />}
                    onClick={handleRegenerate}
                    loading={generating}
                    style={{ borderRadius: 6 }}
                  >
                    重新生成
                  </Button>
                </Space>

                <div style={{ fontSize: 12, color: 'var(--text-sub)', marginTop: 8 }}>
                  {autoSubmit
                    ? '当前为自动提交：点击后将调用破局写接口提交，无需手动复制。'
                    : '当前为手动提交：点击后将内容复制到剪贴板，请粘贴到破局打卡页面。'}
                </div>
              </>
            )}
          </Card>
        </Col>
      </Row>

      {/* 底部：本期打卡记录表 */}
      <Card
        bordered={false}
        style={{ borderRadius: 10, marginTop: 16 }}
        bodyStyle={{ padding: 18 }}
        title={
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <span style={{ fontSize: 14, fontWeight: 600 }}>本期打卡记录</span>
            <span style={{ fontSize: 12, color: 'var(--text-sub)' }}>
              {checkinsSummary(checkins)}
            </span>
          </div>
        }
      >
        <CheckinTable records={checkins} loading={checkinsLoading} />
      </Card>
    </div>
  );
}

// ---------- 子组件：四板块编辑器/展示器 ----------
function DraftEditor({
  draft,
  editing,
  onChange,
}: {
  draft: CheckinDraftOut;
  editing: boolean;
  onChange: (key: DraftKey, val: string) => void;
}) {
  return (
    <div>
      {DRAFT_BLOCKS.map((b) => (
        <div key={b.key} style={{ marginBottom: 14 }}>
          <div
            style={{
              fontSize: 13,
              fontWeight: 600,
              color: 'var(--primary)',
              marginBottom: 6,
            }}
          >
            {b.label}
          </div>
          {editing ? (
            <TextArea
              value={draft[b.key]}
              onChange={(e) => onChange(b.key, e.target.value)}
              autoSize={{ minRows: 2, maxRows: 6 }}
              style={{ borderRadius: 6 }}
            />
          ) : (
            <div
              style={{
                background: 'var(--bg)',
                borderRadius: 6,
                padding: '10px 12px',
                fontSize: 13,
                color: 'var(--text)',
                lineHeight: 1.7,
                whiteSpace: 'pre-wrap',
                minHeight: 36,
              }}
            >
              {draft[b.key] || (
                <span style={{ color: 'var(--text-light)' }}>（空）</span>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ---------- 子组件：打卡记录表 ----------
function CheckinTable({
  records,
  loading,
}: {
  records?: CheckinRecordOut[];
  loading: boolean;
}) {
  const data = useMemo(() => records ?? [], [records]);

  if (!loading && data.length === 0) {
    return <Empty description="本期暂无打卡记录" style={{ padding: 24 }} />;
  }

  return (
    <Table<CheckinRecordOut>
      size="small"
      loading={loading}
      dataSource={data}
      rowKey="id"
      pagination={{ pageSize: 8, showSizeChanger: false, hideOnSinglePage: true }}
      columns={[
        {
          title: '日期',
          dataIndex: 'checkin_date',
          key: 'checkin_date',
          width: 120,
          render: (v: string) => (v ? dayjs(v).format('MM/DD') : '-'),
        },
        {
          title: 'Day',
          dataIndex: 'day_number',
          key: 'day_number',
          width: 80,
          render: (v: number) => (v != null ? `Day${v}` : '-'),
        },
        {
          title: '核心行动',
          dataIndex: 'content',
          key: 'content',
          ellipsis: true,
          render: (v?: string | null) => {
            if (!v) return <span style={{ color: 'var(--text-light)' }}>-</span>;
            // 取"今日行动"作为核心行动摘要
            const m = v.match(/今日行动[：:]\s*([^\n]+)/);
            return m?.[1]?.trim() || v.split('\n')[0] || '-';
          },
        },
        {
          title: '星级',
          dataIndex: 'stars',
          key: 'stars',
          width: 110,
          render: (stars?: number | null, record?: CheckinRecordOut) => {
            if (stars == null) {
              return <span style={{ color: 'var(--text-light)' }}>待评改</span>;
            }
            return (
              <span style={{ color: 'var(--star)', letterSpacing: 2 }}>
                {Array.from({ length: 3 }).map((_, i) => (
                  <span key={i} style={{ opacity: i < stars ? 1 : 0.25 }}>
                    ★
                  </span>
                ))}
              </span>
            );
          },
        },
        {
          title: '状态',
          dataIndex: 'grade_status',
          key: 'grade_status',
          width: 120,
          render: (_: GradeStatus, record: CheckinRecordOut) => {
            return <RecordStatusTag record={record} />;
          },
        },
      ]}
    />
  );
}

// ---------- 子组件：记录状态徽章 ----------
function RecordStatusTag({ record }: { record: CheckinRecordOut }) {
  // 已评改：>=2 星 有效；1 星 无效
  if (record.grade_status === 'graded') {
    if (record.is_valid) return <StatusTag status="valid" text="有效" />;
    return <StatusTag status="invalid" text="无效" />;
  }
  // 待评改：学员已提交，志愿者未评改
  if (record.submitted_at) return <StatusTag status="pending" text="已提交·待评改" />;
  // 草稿
  return <StatusTag status="unknown" text="草稿" />;
}

// ---------- helpers ----------
function syncText(s: string): string {
  switch (s) {
    case 'synced':
      return '已同步';
    case 'pending':
      return '同步中';
    case 'failed':
      return '同步失败';
    case 'manual':
      return '手动模式';
    default:
      return s;
  }
}

function checkinsSummary(records?: CheckinRecordOut[]): string {
  if (!records || records.length === 0) return '本期暂无记录';
  const submitted = records.filter((r) => r.submitted_at).length;
  const valid = records.filter((r) => r.is_valid).length;
  const pending = records.filter(
    (r) => r.submitted_at && r.grade_status !== 'graded'
  ).length;
  return `共 ${records.length} 次 · ${valid} 次有效 · ${pending} 次待评改 · ${submitted} 次已提交`;
}
