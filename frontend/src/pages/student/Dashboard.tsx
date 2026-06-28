import { useMemo } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Card, Row, Col, Tag, Button, Spin, Empty, Progress } from 'antd';
import { CalendarOutlined, ReadOutlined, EditOutlined } from '@ant-design/icons';
import { useCamp } from '@/hooks/useCamps';
import { useTodayTasks, useRoute, useCheckins } from '@/hooks/useStudent';
import DeleteCampButton from '@/components/DeleteCampButton';
import type { CampStatus, CheckinRecordOut } from '@/api/types';
import dayjs from 'dayjs';

/**
 * P3 学员·今日看板（design.md 6.P3 + ui-prototype #student-dashboard）。
 *
 * 页面结构：
 * 1. 页头：标题「今日看板」+ 学员徽章 + 营名 + 起止时间副标题；
 *    右侧按钮组：学习路线 / 手册。
 * 2. 统计 4 卡：训练进度 / 有效打卡 / 距退押金差值 / 已评改 2★以下。
 * 3. 今日任务卡（useTodayTasks）：标题 + 描述 + 标签 + 「生成今日打卡 →」主按钮。
 * 4. 本周任务预览：Day 5~7，今天高亮。
 *
 * 数据源：
 * - useCamp(campId)         营基本信息（名称 / 起止 / 总天数 / 最低打卡天数）
 * - useTodayTasks(campId)   今日任务（day_number / task / progress）
 * - useRoute(campId)        完整学习路线（用于本周预览取 Day5~Day7）
 * - useCheckins(campId)     本期打卡记录（用于计算「2★以下」次数）
 */
export default function StudentDashboard() {
  const params = useParams<{ id: string }>();
  const campId = params.id ? Number(params.id) : undefined;

  // 营详情
  const { data: camp, isLoading: campLoading } = useCamp(campId);
  // 今日任务
  const { data: today, isLoading: todayLoading } = useTodayTasks(campId);
  // 完整学习路线（取 Day5~Day7 用）
  const { data: route } = useRoute(campId);
  // 本期打卡记录（统计 2★以下次数用）
  const { data: checkins } = useCheckins(campId);

  // 本周预览：取 [今天Day, 今天Day+2] 共 3 天的任务
  const weekPreview = useMemo(() => {
    if (!route?.tasks || today?.day_number == null) return [];
    const todayDay = today.day_number;
    return [0, 1, 2].map((offset) => {
      const dayNumber = todayDay + offset;
      return {
        dayNumber,
        task: route.tasks.find((t) => t.day_number === dayNumber) ?? null,
        isToday: offset === 0,
      };
    });
  }, [route, today]);

  // 加载态
  if (campLoading) {
    return (
      <div style={{ padding: 24, textAlign: 'center' }}>
        <Spin />
      </div>
    );
  }

  if (!camp) {
    return (
      <div style={{ padding: 24 }}>
        <Empty description="未找到该行动营" />
      </div>
    );
  }

  // 营状态：未开始 / 进行中 / 已结束
  const campStatus = camp.status as CampStatus;
  const isNotStarted = campStatus === 'not_started';
  const isEnded = campStatus === 'ended';

  // 起止时间副标题
  const dateRange = `${camp.start_date} ~ ${camp.end_date}`;

  return (
    <div style={{ padding: 24 }}>
      {/* ============ 页头 ============ */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 20,
          flexWrap: 'wrap',
          gap: 12,
        }}
      >
        <div>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>
            今日看板{' '}
            <span
              style={{
                background: 'var(--student-bg)',
                color: 'var(--student-fg)',
                borderRadius: 10,
                padding: '2px 10px',
                fontSize: 11,
                fontWeight: 600,
                marginLeft: 6,
                verticalAlign: 'middle',
              }}
            >
              学员
            </span>
          </h2>
          <div style={{ color: 'var(--text-sub)', fontSize: 13, marginTop: 4 }}>
            {camp.name} · {dateRange}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <Link to={`/camp/${campId}/student/route`}>
            <Button icon={<CalendarOutlined />}>学习路线</Button>
          </Link>
          <Link to={`/camp/${campId}/manual`}>
            <Button icon={<ReadOutlined />}>手册</Button>
          </Link>
          <DeleteCampButton campId={camp.id} campName={camp.name} />
        </div>
      </div>

      {/* ============ 营状态提示：未开始 / 已结束 ============ */}
      {(isNotStarted || isEnded) && (
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
          {isNotStarted
            ? `⏳ 行动营尚未开始（${camp.start_date} 开营），今日暂无任务。`
            : '✅ 行动营已结束，可查看完整打卡记录与复盘。'}
        </div>
      )}

      {/* ============ 统计 4 卡 ============ */}
      <Row gutter={[14, 14]} style={{ marginBottom: 20 }}>
        <Col xs={24} sm={12} md={6}>
          <StatCard
            primary={
              <span>
                {camp.current_day ?? 0}{' '}
                <span style={{ fontSize: 14, color: 'var(--text-light)' }}>
                  / {camp.total_days}
                </span>
              </span>
            }
            label="训练进度 Day"
            footer={
              <Progress
                percent={Math.round(
                  ((camp.current_day ?? 0) / Math.max(camp.total_days, 1)) * 100
                )}
                showInfo={false}
                strokeColor="var(--primary)"
                size="small"
              />
            }
          />
        </Col>
        <Col xs={24} sm={12} md={6}>
          <StatCard
            primary={
              <span>
                {camp.valid_days}{' '}
                <span style={{ fontSize: 14, color: 'var(--text-light)' }}>
                  / {camp.min_checkin_days}
                </span>
              </span>
            }
            label="有效打卡（2★+）"
            footer={
              <Progress
                percent={Math.round(
                  (camp.valid_days / Math.max(camp.min_checkin_days, 1)) * 100
                )}
                showInfo={false}
                strokeColor="var(--success)"
                size="small"
              />
            }
          />
        </Col>
        <Col xs={24} sm={12} md={6}>
          <StatCard
            primary={(
              <span
                style={{
                  color:
                    camp.valid_days >= camp.min_checkin_days
                      ? 'var(--success)'
                      : 'var(--warning)',
                }}
              >
                {Math.max(camp.min_checkin_days - camp.valid_days, 0)}
              </span>
            )}
            label="距退押金还差"
            hint={
              camp.valid_days >= camp.min_checkin_days ? '已达标，可退押金' : '还需 N 天有效打卡'
            }
          />
        </Col>
        <Col xs={24} sm={12} md={6}>
          <StatCard
            primary={
              <span
                style={{
                  color:
                    countBelowTwoStars(checkins) > 0 ? 'var(--danger)' : undefined,
                }}
              >
                {countBelowTwoStars(checkins)}
              </span>
            }
            label="已评改 2★ 以下"
            hint="已评改且 1★ 的次数"
          />
        </Col>
      </Row>

      {/* ============ 今日任务卡 ============ */}
      <Card
        title={
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              fontSize: 14,
              fontWeight: 600,
            }}
          >
            <span>
              {today?.task ? `📌 今日任务 · Day ${today.day_number}` : '📌 今日任务'}
            </span>
            <span style={{ fontSize: 12, color: 'var(--text-sub)', fontWeight: 400 }}>
              {dayjs().format('YYYY/MM/DD')}（{weekdayCn(dayjs().day())}）
            </span>
          </div>
        }
        style={{ marginBottom: 16, borderRadius: 10 }}
        bodyStyle={{ padding: 18 }}
      >
        {todayLoading ? (
          <div style={{ textAlign: 'center', padding: 24 }}>
            <Spin />
          </div>
        ) : today?.task ? (
          <>
            <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 6 }}>
              {today.task.title}
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-sub)', lineHeight: 1.7 }}>
              {today.task.description || '（暂无任务描述）'}
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 16 }}>
              {renderTaskTags(today.task.tags)}
            </div>
            <div style={{ display: 'flex', gap: 12, marginTop: 20 }}>
              <Link to={`/camp/${campId}/student/checkin`}>
                <Button type="primary" icon={<EditOutlined />}>
                  ✍️ 生成今日打卡 →
                </Button>
              </Link>
              <Link to={`/camp/${campId}/student/route`}>
                <Button>查看完整学习路线</Button>
              </Link>
            </div>
          </>
        ) : (
          <Empty description="今日暂无任务，请先到学习路线检查或上传手册" />
        )}
      </Card>

      {/* ============ 本周任务预览 ============ */}
      <Card
        title={
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              fontSize: 14,
              fontWeight: 600,
            }}
          >
            <span>🗓 本周任务预览</span>
            <span style={{ fontSize: 12, color: 'var(--text-light)', fontWeight: 400 }}>
              {weekPreview.length > 0
                ? `Day ${weekPreview[0]?.dayNumber} ~ Day ${weekPreview[weekPreview.length - 1]?.dayNumber}`
                : '暂无'}
            </span>
          </div>
        }
        style={{ borderRadius: 10 }}
        bodyStyle={{ padding: 0 }}
      >
        {weekPreview.length === 0 ? (
          <div style={{ padding: 24 }}>
            <Empty description="请先生成学习路线" />
          </div>
        ) : (
          weekPreview.map((item, idx) => (
            <div
              key={item.dayNumber}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '12px 18px',
                background: item.isToday ? 'var(--primary-light)' : 'transparent',
                borderBottom:
                  idx === weekPreview.length - 1 ? 'none' : '1px solid var(--border)',
                borderRadius: item.isToday ? 6 : 0,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <Tag
                  style={{
                    background: item.isToday ? 'var(--primary)' : '#f3f4f6',
                    color: item.isToday ? '#fff' : 'var(--text-sub)',
                    border: 'none',
                    borderRadius: 10,
                    padding: '2px 10px',
                    fontSize: 11,
                    fontWeight: 600,
                    margin: 0,
                  }}
                >
                  {`Day${item.dayNumber}${item.isToday ? '·今天' : ''}`}
                </Tag>
                <span style={{ fontSize: 13.5 }}>
                  {item.task?.title ?? '（尚未规划，可在学习路线编辑）'}
                </span>
              </div>
              <span style={{ fontSize: 12, color: 'var(--text-light)' }}>
                {item.isToday ? '进行中' : '未开始'}
              </span>
            </div>
          ))
        )}
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 子组件
// ---------------------------------------------------------------------------

interface StatCardProps {
  primary: React.ReactNode;
  label: string;
  hint?: string;
  footer?: React.ReactNode;
}

/**
 * 统计卡（design.md 4.5 stat：大数字 + 标签）。
 */
function StatCard({ primary, label, hint, footer }: StatCardProps) {
  return (
    <Card
      style={{ borderRadius: 10, height: '100%' }}
      bodyStyle={{ padding: 16 }}
    >
      <div style={{ fontSize: 26, fontWeight: 700, lineHeight: 1.2 }}>{primary}</div>
      <div style={{ fontSize: 12, color: 'var(--text-sub)', marginTop: 4 }}>{label}</div>
      {hint && (
        <div style={{ fontSize: 11, color: 'var(--text-light)', marginTop: 6 }}>{hint}</div>
      )}
      {footer && <div style={{ marginTop: 10 }}>{footer}</div>}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// 工具函数
// ---------------------------------------------------------------------------

/**
 * 统计已评改且星级 < 2 的打卡次数。
 * 仅统计 grade_status === 'graded' 且 stars === 1 的记录。
 */
function countBelowTwoStars(checkins: CheckinRecordOut[] | undefined): number {
  if (!checkins) return 0;
  return checkins.filter(
    (c) => c.grade_status === 'graded' && c.stars != null && c.stars < 2
  ).length;
}

/**
 * 把今日任务 tags（自由 JSON 数组）渲染为小标签 chip。
 * 兼容三种常见字段：chapter / type / duration_minutes / label。
 */
function renderTaskTags(tags: Array<Record<string, unknown>> | null | undefined) {
  if (!tags || tags.length === 0) return null;
  const labelOf = (raw: Record<string, unknown>): string => {
    const chapter = raw.chapter ?? raw.chapter_label;
    const type = raw.type ?? raw.kind;
    const duration = raw.duration_minutes ?? raw.duration;
    const label = raw.label ?? raw.text;
    if (typeof label === 'string') return label;
    const parts: string[] = [];
    if (chapter) parts.push(`手册${chapter}`);
    if (type) parts.push(String(type));
    if (duration) parts.push(`预计 ${duration} 分钟`);
    return parts.join(' · ') || JSON.stringify(raw);
  };
  return tags.map((t, i) => {
    const text = labelOf(t);
    return (
      <Tag
        key={i}
        style={{
          background: '#f3f4f6',
          color: 'var(--text-sub)',
          border: 'none',
          borderRadius: 5,
          padding: '2px 8px',
          fontSize: 11,
          fontWeight: 600,
          margin: 0,
        }}
      >
        {text}
      </Tag>
    );
  });
}

/** 数字 0~6 → 中文「日一二三四五六」。 */
function weekdayCn(d: number): string {
  return ['日', '一', '二', '三', '四', '五', '六'][d] ?? '';
}