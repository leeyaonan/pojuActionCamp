import { useMemo } from 'react';
import {
  Button,
  Card,
  Col,
  Collapse,
  Descriptions,
  Empty,
  Row,
  Skeleton,
  Space,
  Spin,
  Tag,
  Timeline,
  Typography,
} from 'antd';
import {
  ArrowLeftOutlined,
  CommentOutlined,
  EditOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { useNavigate, useParams } from 'react-router-dom';
import dayjs from 'dayjs';

import { useStudentArchive } from '@/hooks/useVolunteer';
import StarPicker from '@/components/StarPicker';
import type { ArchiveTimelineItem, StudentSummary } from '@/api/types';

const { Text, Title } = Typography;

/**
 * P8 志愿者·学员档案（volunteer-archive）
 *
 * 页面结构（对齐 design.md P8 + ui-prototype P: VOLUNTEER-ARCHIVE）：
 *  - 页头：标题"学员档案" + 志愿者徽章 + 副标题"仅志愿者可见" + "← 返回学员看板"
 *  - 黄色提示条："学员档案仅志愿者侧可见，学员本人不可见"
 *  - 统计 4 卡：学员昵称 / 有效打卡 N/min / 距目标差 / 平均星级
 *  - 时间线（来自 useStudentArchive）：逐项 Card 显示 日期/Day/主题 + 星级（StarPicker 只读）+
 *    内容摘要 + 评语；待评改项橙 badge；无效项评语区红底
 *  - 底部："为 DayX 打卡评改"按钮（跳转 grading）+ "返回"按钮
 *
 * 数据来源：
 *  - GET /api/students/{id} → StudentArchive = { student, stats, timeline[] }
 *  - timeline 项含 day_number / checkin_date / content / stars / is_valid / grade_status
 */

export default function VolunteerArchive() {
  const navigate = useNavigate();
  const params = useParams<{ id: string; studentId: string }>();
  const campId = Number(params.id);
  const studentId = Number(params.studentId);

  const { data, isLoading, isError, error, refetch } = useStudentArchive(
    Number.isFinite(studentId) && studentId > 0 ? studentId : undefined
  );

  // 推导"下一个待评改的 Day"（用于底部跳转按钮文案与目标）
  const nextPending = useMemo<ArchiveTimelineItem | undefined>(() => {
    if (!data?.timeline) return undefined;
    return data.timeline.find(
      (t) =>
        t.grade_status === 'pending' ||
        (t.stars == null && t.grade_status !== 'graded')
    );
  }, [data]);

  const nextDayNumber =
    nextPending?.day_number ??
    data?.timeline?.[0]?.day_number ??
    data?.student?.current_day ??
    null;

  const backToBoard = () => {
    if (Number.isFinite(campId) && campId > 0) {
      navigate(`/camp/${campId}/volunteer`);
    } else {
      navigate('/');
    }
  };

  const goGrading = () => {
    if (Number.isFinite(campId) && campId > 0) {
      navigate(`/camp/${campId}/volunteer/grade`);
    }
  };

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
          flexWrap: 'wrap',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Title
              level={3}
              style={{ margin: 0, fontSize: 20, fontWeight: 700 }}
            >
              学员档案
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
            仅志愿者可见 · 用于评改时参考历史作业
          </Text>
        </div>
        <Button
          icon={<ArrowLeftOutlined />}
          onClick={backToBoard}
          style={{ borderRadius: 6 }}
        >
          返回学员看板
        </Button>
      </div>

      {/* 黄色提示条 */}
      <div
        style={{
          background: 'var(--warning-bg, #fef3c7)',
          border: '1px solid #fde68a',
          borderRadius: 6,
          padding: '10px 14px',
          fontSize: 13,
          color: '#92400e',
          marginBottom: 16,
        }}
      >
        学员档案仅志愿者侧可见，学员本人不可见。每次评改时 AI 会参考此档案判断进步与原创性。
      </div>

      {/* 错误态 */}
      {isError && !isLoading && (
        <Card
          bordered={false}
          style={{ borderRadius: 10, marginBottom: 16 }}
          bodyStyle={{ padding: 18 }}
        >
          <Empty
            description={
              <span>
                学员档案加载失败：
                {(error as Error | undefined)?.message ?? '未知错误'}
              </span>
            }
          >
            <Button type="primary" onClick={() => refetch()}>
              重试
            </Button>
          </Empty>
        </Card>
      )}

      {/* 加载骨架 */}
      {isLoading && !data && (
        <Card
          bordered={false}
          style={{ borderRadius: 10 }}
          bodyStyle={{ padding: 18 }}
        >
          <Skeleton active paragraph={{ rows: 6 }} />
        </Card>
      )}

      {/* 统计 4 卡 */}
      {data && (
        <>
          <Row gutter={[14, 14]} style={{ marginBottom: 20 }}>
            <StatCard
              label="学员昵称"
              value={data.student?.nickname ?? '-'}
              valueNode={
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                  <UserOutlined style={{ color: 'var(--primary)' }} />
                  {data.student?.nickname ?? '-'}
                </span>
              }
            />
            <StatCard
              label="有效打卡"
              value={`${data.stats?.valid_days ?? 0} / ${
                data.student?.gap_to_min != null
                  ? (data.stats?.valid_days ?? 0) + Math.max(0, data.student.gap_to_min)
                  : '-'
              }`}
              tone="primary"
            />
            <StatCard
              label="距目标还差"
              value={data.stats?.gap_to_min ?? 0}
              tone={
                (data.stats?.gap_to_min ?? 0) > 0 ? 'warn' : 'success'
              }
            />
            <StatCard
              label="平均星级"
              value={
                data.stats?.avg_stars != null
                  ? Number(data.stats.avg_stars).toFixed(1)
                  : '-'
              }
              tone="star"
            />
          </Row>

          {/* 档案详情（迁移 0004 起的扩展字段） */}
          <ProfileCard student={data.student} />

          {/* 时间线 */}
          <Card
            bordered={false}
            style={{ borderRadius: 10, marginBottom: 16 }}
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
                  打卡与评改时间线
                </span>
                <span style={{ fontSize: 12, color: 'var(--text-sub)' }}>
                  共 {data.timeline?.length ?? 0} 次打卡
                </span>
              </div>
            }
          >
            {!data.timeline || data.timeline.length === 0 ? (
              <Empty description="暂无打卡记录" style={{ padding: 24 }} />
            ) : (
              <TimelineList timeline={data.timeline} />
            )}
          </Card>

          {/* 底部按钮区 */}
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <Button
              type="primary"
              icon={<EditOutlined />}
              onClick={goGrading}
              style={{ borderRadius: 6 }}
            >
              为 Day{nextDayNumber ?? '?'} 打卡评改
            </Button>
            <Button
              icon={<ArrowLeftOutlined />}
              onClick={backToBoard}
              style={{ borderRadius: 6 }}
            >
              返回学员看板
            </Button>
          </div>
        </>
      )}
    </div>
  );
}

// ---------- 子组件：统计卡 ----------
function StatCard({
  label,
  value,
  valueNode,
  tone,
}: {
  label: string;
  value: string | number;
  valueNode?: React.ReactNode;
  tone?: 'primary' | 'warn' | 'success' | 'star';
}) {
  const color = (() => {
    switch (tone) {
      case 'warn':
        return 'var(--warning)';
      case 'success':
        return 'var(--success)';
      case 'star':
        return 'var(--star)';
      case 'primary':
        return 'var(--primary)';
      default:
        return 'var(--text)';
    }
  })();

  return (
    <Col xs={24} sm={12} md={6}>
      <Card
        bordered={false}
        style={{ borderRadius: 10 }}
        bodyStyle={{ padding: 16 }}
      >
        <div
          style={{
            fontSize: 24,
            fontWeight: 700,
            lineHeight: 1.2,
            color,
            display: 'flex',
            alignItems: 'baseline',
            gap: 6,
          }}
        >
          {valueNode ?? value}
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-sub)', marginTop: 6 }}>
          {label}
        </div>
      </Card>
    </Col>
  );
}

// ---------- 子组件：档案详情（迁移 0004 起的扩展字段） ----------
function ProfileCard({ student }: { student: StudentSummary | undefined }) {
  // 字段为空时统一展示 "-"；空集合判断：所有档案字段全空 → 提示尚未同步档案。
  const dash = '-';
  const v = (x?: string | number | null) =>
    x === null || x === undefined || x === '' ? dash : x;

  const allEmpty =
    !student ||
    [
      student.full_name,
      student.wechat_id,
      student.phone,
      student.wechat_name,
      student.user_name,
      student.user_number,
      student.leader_name,
      student.leader_user_name,
      student.leader_wechat_id,
      student.volunteer_name,
      student.volunteer_user_name,
      student.volunteer_wechat_id,
      student.data_officer_name,
      student.data_officer_user_name,
      student.data_officer_wechat_id,
      student.clock_in_count,
      student.camp_days,
    ].every((x) => x === null || x === undefined);

  return (
    <Card
      bordered={false}
      style={{ borderRadius: 10, marginBottom: 16 }}
      bodyStyle={{ padding: 18 }}
      title={
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <span style={{ fontSize: 14, fontWeight: 600 }}>学员档案详情</span>
          <span style={{ fontSize: 12, color: 'var(--text-sub)' }}>
            {student?.last_synced_at
              ? `最近同步 ${dayjs(student.last_synced_at).format('MM/DD HH:mm')}`
              : ''}
          </span>
        </div>
      }
    >
      <Collapse
        defaultActiveKey={[]}
        ghost
        size="small"
        items={[
          {
            key: 'profile',
            label: (
              <span style={{ fontSize: 13, color: 'var(--text-sub)' }}>
                展开查看档案详情（含姓名/微信号/组长/志愿者/数据官/打卡统计）
              </span>
            ),
            children: allEmpty ? (
              <Empty
                description={
                  <span style={{ color: 'var(--text-sub)' }}>
                    尚未从破局同步学员档案，请先在「学员看板」执行「初始化档案」
                  </span>
                }
                style={{ padding: 16 }}
              />
            ) : (
              <>
                <Descriptions
                  size="small"
                  column={{ xs: 1, sm: 2, md: 3 }}
                  labelStyle={{ color: 'var(--text-sub)', width: 96 }}
                  title={
                    <span style={{ fontSize: 13, fontWeight: 600 }}>
                      学员本人
                    </span>
                  }
                  items={[
                    { key: 'full_name', label: '姓名', children: v(student?.full_name) },
                    { key: 'wechat_name', label: '微信昵称', children: v(student?.wechat_name) },
                    { key: 'wechat_id', label: '微信号', children: v(student?.wechat_id) },
                    { key: 'phone', label: '手机号', children: v(student?.phone) },
                    { key: 'user_name', label: '破局账号', children: v(student?.user_name) },
                    { key: 'user_number', label: '破局编号', children: v(student?.user_number) },
                  ]}
                />
                <Descriptions
                  size="small"
                  column={{ xs: 1, sm: 2, md: 3 }}
                  labelStyle={{ color: 'var(--text-sub)', width: 96 }}
                  style={{ marginTop: 12 }}
                  title={
                    <span style={{ fontSize: 13, fontWeight: 600 }}>组长</span>
                  }
                  items={[
                    { key: 'leader_name', label: '姓名', children: v(student?.leader_name) },
                    { key: 'leader_user_name', label: '账号', children: v(student?.leader_user_name) },
                    { key: 'leader_wechat_id', label: '微信', children: v(student?.leader_wechat_id) },
                  ]}
                />
                <Descriptions
                  size="small"
                  column={{ xs: 1, sm: 2, md: 3 }}
                  labelStyle={{ color: 'var(--text-sub)', width: 96 }}
                  style={{ marginTop: 12 }}
                  title={
                    <span style={{ fontSize: 13, fontWeight: 600 }}>志愿者</span>
                  }
                  items={[
                    { key: 'volunteer_name', label: '姓名', children: v(student?.volunteer_name) },
                    { key: 'volunteer_user_name', label: '账号', children: v(student?.volunteer_user_name) },
                    { key: 'volunteer_wechat_id', label: '微信', children: v(student?.volunteer_wechat_id) },
                  ]}
                />
                <Descriptions
                  size="small"
                  column={{ xs: 1, sm: 2, md: 3 }}
                  labelStyle={{ color: 'var(--text-sub)', width: 96 }}
                  style={{ marginTop: 12 }}
                  title={
                    <span style={{ fontSize: 13, fontWeight: 600 }}>数据官</span>
                  }
                  items={[
                    { key: 'data_officer_name', label: '姓名', children: v(student?.data_officer_name) },
                    { key: 'data_officer_user_name', label: '账号', children: v(student?.data_officer_user_name) },
                    { key: 'data_officer_wechat_id', label: '微信', children: v(student?.data_officer_wechat_id) },
                  ]}
                />
                <Descriptions
                  size="small"
                  column={{ xs: 1, sm: 2, md: 3 }}
                  labelStyle={{ color: 'var(--text-sub)', width: 96 }}
                  style={{ marginTop: 12 }}
                  title={
                    <span style={{ fontSize: 13, fontWeight: 600 }}>打卡统计</span>
                  }
                  items={[
                    { key: 'clock_in_count', label: '已打卡次数', children: v(student?.clock_in_count) },
                    { key: 'camp_days', label: '行动营总天数', children: v(student?.camp_days) },
                  ]}
                />
              </>
            ),
          },
        ]}
      />
    </Card>
  );
}

// ---------- 子组件：时间线 ----------
function TimelineList({ timeline }: { timeline: ArchiveTimelineItem[] }) {
  // 已有评语解析（后端 ArchiveTimelineItem 类型暂未含评文字段，这里通过 content
  // 中"评语：xxx"片段做兜底提取；后续后端加字段可替换）。
  const items = useMemo(
    () =>
      timeline.map((item) => ({
        ...item,
        parsed: parseComment(item.content),
      })),
    [timeline]
  );

  return (
    <Timeline
      style={{ marginTop: 4 }}
      items={items.map((item) => ({
        dot: itemDotColor(item.grade_status),
        color: itemDotColor(item.grade_status),
        children: (
          <TimelineCard item={item} />
        ),
      }))}
    />
  );
}

// ---------- 子组件：时间线单卡片 ----------
function TimelineCard({
  item,
}: {
  item: ArchiveTimelineItem & {
    parsed: { summary: string; comment?: string };
  };
}) {
  const isPending =
    item.grade_status === 'pending' ||
    (item.stars == null && item.grade_status !== 'graded');

  return (
    <Card
      size="small"
      bordered
      style={{
        borderRadius: 8,
        border: '1px solid var(--border)',
        marginBottom: 4,
      }}
      bodyStyle={{ padding: '12px 14px' }}
    >
      {/* 头部：日期 / Day / 主题 + 状态徽章 / 星级 */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 12,
          flexWrap: 'wrap',
        }}
      >
        <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>
          Day{item.day_number ?? '-'}
          {item.checkin_date && (
            <span
              style={{
                color: 'var(--text-sub)',
                fontWeight: 400,
                marginLeft: 8,
              }}
            >
              {dayjs(item.checkin_date).format('MM/DD')}
            </span>
          )}
        </div>
        <Space size={10} align="center">
          {isPending && (
            <Tag
              style={{
                background: 'var(--warning-bg, #fef3c7)',
                color: 'var(--warning)',
                border: 'none',
                borderRadius: 10,
                padding: '0 8px',
                fontSize: 11,
                margin: 0,
              }}
            >
              待评改
            </Tag>
          )}
          {item.grade_status === 'graded' && item.is_valid && (
            <Tag
              style={{
                background: '#dcfce7',
                color: 'var(--success)',
                border: 'none',
                borderRadius: 10,
                padding: '0 8px',
                fontSize: 11,
                margin: 0,
              }}
            >
              已评改 · 有效
            </Tag>
          )}
          {item.grade_status === 'graded' && !item.is_valid && (
            <Tag
              style={{
                background: '#fee2e2',
                color: 'var(--danger)',
                border: 'none',
                borderRadius: 10,
                padding: '0 8px',
                fontSize: 11,
                margin: 0,
              }}
            >
              已评改 · 无效
            </Tag>
          )}
          {/* 只读星级 */}
          <span aria-label={`${item.stars ?? 0} 星`}>
            <StarPicker value={item.stars ?? 0} disabled allowClear={false} />
          </span>
        </Space>
      </div>

      {/* 内容摘要 */}
      <div
        style={{
          marginTop: 8,
          fontSize: 13,
          color: 'var(--text)',
          lineHeight: 1.7,
          whiteSpace: 'pre-wrap',
        }}
      >
        {item.parsed.summary || (
          <span style={{ color: 'var(--text-light)' }}>（无内容摘要）</span>
        )}
      </div>

      {/* 评语：无效打卡红底，已评改有效淡底，待评改无评语 */}
      {item.parsed.comment && (
        <div
          style={{
            marginTop: 10,
            padding: '10px 12px',
            borderRadius: 6,
            fontSize: 12,
            lineHeight: 1.6,
            background: commentBg(item),
            color: commentFg(item),
            border: commentBorder(item),
            display: 'flex',
            gap: 6,
            alignItems: 'flex-start',
          }}
        >
          <CommentOutlined style={{ marginTop: 2 }} />
          <span>
            <strong style={{ marginRight: 4 }}>评语：</strong>
            {item.parsed.comment}
          </span>
        </div>
      )}
    </Card>
  );
}

// ---------- helpers ----------

/** 时间线节点颜色：待评改=橙，已评改有效=绿，无效=红 */
function itemDotColor(status: string): string {
  if (status === 'graded') return 'var(--success)';
  if (status === 'pending') return 'var(--warning)';
  return 'var(--primary)';
}

/** 评语区底色：无效打卡红底 */
function commentBg(item: ArchiveTimelineItem): string {
  if (item.grade_status === 'graded' && !item.is_valid) {
    return 'var(--danger-bg, #fee2e2)';
  }
  if (item.grade_status === 'graded' && item.is_valid) {
    return 'var(--bg)';
  }
  return 'var(--bg)';
}

/** 评语区前景色：无效打卡红字 */
function commentFg(item: ArchiveTimelineItem): string {
  if (item.grade_status === 'graded' && !item.is_valid) {
    return 'var(--danger)';
  }
  return 'var(--text-sub)';
}

/** 评语区边框 */
function commentBorder(item: ArchiveTimelineItem): string {
  if (item.grade_status === 'graded' && !item.is_valid) {
    return '1px solid #fecaca';
  }
  return '1px solid var(--border)';
}

/**
 * 从 content 字符串中提取"内容摘要 + 评语"。
 *
 * 后端 ArchiveTimelineItem.content 当前为打卡正文（可能含四板块拼接）。
 * 这里做兼容解析：
 *  - 若 content 中带"评语：xxx"片段，则评语 = xxx，摘要 = 评语前的内容；
 *  - 否则摘要 = 原 content。
 */
function parseComment(
  raw?: string | null
): { summary: string; comment?: string } {
  if (!raw) return { summary: '' };
  const m = raw.match(/(?:^|\n)\s*评语[：:]\s*([^\n]+)/);
  if (m) {
    const comment = m[1].trim();
    const summary = raw.replace(m[0], '').trim();
    return { summary, comment };
  }
  return { summary: raw };
}

// Spin 占位导出（保留供后续扩展使用，避免未用告警）
export { Spin };
