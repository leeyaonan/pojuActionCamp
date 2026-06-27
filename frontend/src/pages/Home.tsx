import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { Row, Col, Card, Progress, Empty, Spin, Button, Tooltip, Tag } from 'antd';
import {
  PlusOutlined,
  CalendarOutlined,
  ThunderboltOutlined,
  CheckCircleOutlined,
  EditOutlined,
  TeamOutlined,
  UserOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { useCamps } from '@/hooks/useCamps';
import StatusTag, { type StatusKey } from '@/components/Tag';
import type { CampSummary, CampStatus, Role } from '@/api/types';

/**
 * P1 行动营列表（首页）。
 *
 * 结构：
 *  - 页头：标题"我的行动营" + 副标题 + ＋ 新建行动营 主按钮
 *  - 统计 4 卡：进行中 / 已结束 / 学员身份 / 志愿者身份
 *  - 行动营卡片网格：身份徽章 + 状态徽章 + 名称 + 起止 + 进度条 + 关键数字
 *  - 学员卡：显示 Day x/N + 有效打卡 x / 最低天数
 *  - 志愿者卡：显示 待评改数 + 进行中学员数（暂用占位数字，后续接真实接口）
 *  - 已结束卡 opacity 0.65
 */
export default function Home() {
  const { data: camps, isLoading } = useCamps();

  // 统计（按 status / role 计数）
  const stats = useMemo(() => {
    const list = camps ?? [];
    return {
      ongoing: list.filter((c) => c.status === 'ongoing').length,
      ended: list.filter((c) => c.status === 'ended').length,
      notStarted: list.filter((c) => c.status === 'not_started').length,
      student: list.filter((c) => c.role === 'student').length,
      volunteer: list.filter((c) => c.role === 'volunteer').length,
      total: list.length,
    };
  }, [camps]);

  return (
    <div style={{ padding: '8px 4px 24px' }}>
      {/* 页头 */}
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          marginBottom: 20,
          gap: 12,
          flexWrap: 'wrap',
        }}
      >
        <div>
          <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--text)' }}>
            我的行动营
          </div>
          <div style={{ color: 'var(--text-sub)', fontSize: 13, marginTop: 4 }}>
            管理你的学员营与志愿者营，点击卡片进入对应身份工作台
          </div>
        </div>
        <Link to="/create">
          <Button type="primary" icon={<PlusOutlined />} size="middle">
            新建行动营
          </Button>
        </Link>
      </div>

      {/* 统计 4 卡 */}
      <Row gutter={[14, 14]} style={{ marginBottom: 20 }}>
        <Col xs={12} sm={12} md={6}>
          <StatCard
            num={stats.ongoing}
            label="进行中"
            accent="primary"
            icon={<ThunderboltOutlined />}
            tooltip={`含未开始 ${stats.notStarted} 个，进入营后再开始计时`}
          />
        </Col>
        <Col xs={12} sm={12} md={6}>
          <StatCard
            num={stats.ended}
            label="已结束"
            accent="sub"
            icon={<CheckCircleOutlined />}
          />
        </Col>
        <Col xs={12} sm={12} md={6}>
          <StatCard
            num={stats.student}
            label="学员身份"
            accent="student"
            icon={<UserOutlined />}
          />
        </Col>
        <Col xs={12} sm={12} md={6}>
          <StatCard
            num={stats.volunteer}
            label="志愿者身份"
            accent="volunteer"
            icon={<TeamOutlined />}
          />
        </Col>
      </Row>

      {/* 行动营卡片列表 */}
      <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>
          全部行动营
          <span style={{ marginLeft: 8, fontSize: 12, color: 'var(--text-sub)', fontWeight: 400 }}>
            共 {stats.total} 个
          </span>
        </div>
      </div>

      {isLoading ? (
        <div style={{ padding: 48, textAlign: 'center' }}>
          <Spin />
        </div>
      ) : !camps || camps.length === 0 ? (
        <EmptyState />
      ) : (
        <Row gutter={[16, 16]}>
          {camps.map((camp) => (
            <Col key={camp.id} xs={24} sm={12} md={12} lg={8} xl={6}>
              <CampCard camp={camp} />
            </Col>
          ))}
        </Row>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 统计卡
// ---------------------------------------------------------------------------

type AccentKey = 'primary' | 'sub' | 'student' | 'volunteer';

const ACCENT_COLOR: Record<AccentKey, string> = {
  primary: 'var(--primary)',
  sub: 'var(--text-sub)',
  student: 'var(--student-fg)',
  volunteer: 'var(--volunteer-fg)',
};

const ACCENT_BG: Record<AccentKey, string> = {
  primary: 'var(--primary-light)',
  sub: 'var(--bg)',
  student: 'var(--student-bg)',
  volunteer: 'var(--volunteer-bg)',
};

function StatCard({
  num,
  label,
  accent,
  icon,
  tooltip,
}: {
  num: number;
  label: string;
  accent: AccentKey;
  icon?: React.ReactNode;
  tooltip?: string;
}) {
  const color = ACCENT_COLOR[accent];
  const bg = ACCENT_BG[accent];
  const card = (
    <Card
      hoverable={false}
      style={{
        borderRadius: 10,
        boxShadow: 'var(--shadow-card)',
        border: '1px solid var(--border)',
      }}
      styles={{ body: { padding: 16 } }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <div style={{ fontSize: 26, fontWeight: 700, color, lineHeight: 1.1 }}>{num}</div>
          <div style={{ fontSize: 12, color: 'var(--text-sub)', marginTop: 6 }}>{label}</div>
        </div>
        {icon ? (
          <div
            style={{
              width: 36,
              height: 36,
              borderRadius: 8,
              background: bg,
              color,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 18,
            }}
          >
            {icon}
          </div>
        ) : null}
      </div>
    </Card>
  );
  if (tooltip) {
    return <Tooltip title={tooltip}>{card}</Tooltip>;
  }
  return card;
}

// ---------------------------------------------------------------------------
// 空状态
// ---------------------------------------------------------------------------

function EmptyState() {
  return (
    <Card
      style={{
        borderRadius: 10,
        border: '1px dashed var(--border)',
        boxShadow: 'none',
      }}
      styles={{ body: { padding: 56 } }}
    >
      <Empty
        image={
          <div
            style={{
              fontSize: 48,
              color: 'var(--text-light)',
              lineHeight: 1,
            }}
          >
            📋
          </div>
        }
        description={
          <div>
            <div style={{ fontSize: 14, color: 'var(--text)', fontWeight: 600 }}>
              还没有任何行动营
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-sub)', marginTop: 4 }}>
              点击右上角"新建行动营"开始你的第一次训练
            </div>
          </div>
        }
      >
        <Link to="/create">
          <Button type="primary" icon={<PlusOutlined />}>
            立即新建
          </Button>
        </Link>
      </Empty>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// 行动营卡片
// ---------------------------------------------------------------------------

function CampCard({ camp }: { camp: CampSummary }) {
  const isEnded = camp.status === 'ended';
  const isStudent = camp.role === 'student';
  const statusKey = camp.status as StatusKey;
  const percent = clampPercent(Math.round((camp.progress ?? 0) * 100));

  // 跳转目标：学员→今日看板；志愿者→学员看板
  const target = isStudent
    ? `/camp/${camp.id}/student`
    : `/camp/${camp.id}/volunteer`;

  const roleIcon = isStudent ? <UserOutlined /> : <TeamOutlined />;

  return (
    <Link to={target} style={{ display: 'block' }}>
      <Card
        hoverable
        style={{
          borderRadius: 10,
          border: '1px solid var(--border)',
          boxShadow: 'var(--shadow-card)',
          opacity: isEnded ? 0.65 : 1,
          transition: 'box-shadow .15s, transform .15s',
        }}
        styles={{ body: { padding: 16 } }}
      >
        {/* 顶部：身份徽章 + 状态徽章 */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: 10,
          }}
        >
          <RoleBadge role={camp.role as Role} icon={roleIcon} />
          <StatusTag status={statusKey} />
        </div>

        {/* 名称 */}
        <div
          style={{
            fontSize: 15,
            fontWeight: 600,
            color: 'var(--text)',
            marginBottom: 6,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
          title={camp.name}
        >
          {camp.name}
        </div>

        {/* 起止 + 总天数 */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            fontSize: 12,
            color: 'var(--text-sub)',
            marginBottom: 12,
          }}
        >
          <CalendarOutlined />
          <span>
            {camp.start_date} ~ {camp.end_date}
          </span>
          <span style={{ color: 'var(--text-light)' }}>· 共 {camp.total_days} 天</span>
        </div>

        {/* 进度条 */}
        <Tooltip title={`训练进度 ${percent}%`}>
          <Progress
            percent={percent}
            showInfo={false}
            strokeColor="var(--primary)"
            trailColor="#eef0f3"
            size={{ height: 8 }}
          />
        </Tooltip>

        {/* 底部数字：学员/志愿者 显示不同 */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginTop: 10,
            fontSize: 12,
          }}
        >
          {isStudent ? (
            <StudentMetrics camp={camp} />
          ) : (
            <VolunteerMetrics camp={camp} />
          )}
        </div>
      </Card>
    </Link>
  );
}

// 学员侧关键数字：Day x/N + 有效打卡 x / 最低天数
function StudentMetrics({ camp }: { camp: CampSummary }) {
  const day = camp.current_day ?? 0;
  const valid = camp.valid_days ?? 0;
  const min = camp.min_checkin_days ?? 0;
  const short = valid < min;

  return (
    <>
      <span style={{ color: 'var(--text-sub)' }}>
        Day <span style={{ color: 'var(--text)', fontWeight: 600 }}>{day}</span>
        <span style={{ color: 'var(--text-light)' }}>/{camp.total_days}</span>
      </span>
      <span
        style={{
          color: short ? 'var(--danger)' : 'var(--success)',
          display: 'inline-flex',
          alignItems: 'center',
          gap: 4,
          fontWeight: 500,
        }}
        title={short ? '有效打卡不足最低天数' : '有效打卡达标'}
      >
        {short ? <WarningOutlined /> : <CheckCircleOutlined />}
        有效 {valid}
        <span style={{ color: 'var(--text-light)' }}>/{min}</span>
      </span>
    </>
  );
}

// 志愿者侧关键数字：待评改数（占位，后续接入真实接口）
// 当前 MVP 暂未对接志愿者看板数据，先展示可读性占位
function VolunteerMetrics({ camp }: { camp: CampSummary }) {
  // TODO: 接真实待评改/进行中学员数；MVP 暂用占位（避免假数据误导，统一显示短横线 + 提示）
  return (
    <>
      <span style={{ color: 'var(--text-sub)' }}>
        Day <span style={{ color: 'var(--text)', fontWeight: 600 }}>{camp.current_day ?? 0}</span>
        <span style={{ color: 'var(--text-light)' }}>/{camp.total_days}</span>
      </span>
      <Tooltip title="进入学员看板后可查看待评改数">
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 4,
            color: 'var(--text-sub)',
            background: 'var(--bg)',
            padding: '2px 8px',
            borderRadius: 10,
            fontSize: 11,
            fontWeight: 600,
          }}
        >
          <EditOutlined />
          待评改 · 进入查看
        </span>
      </Tooltip>
    </>
  );
}

// ---------------------------------------------------------------------------
// 身份徽章
// ---------------------------------------------------------------------------

function RoleBadge({ role, icon }: { role: Role; icon?: React.ReactNode }) {
  const bg = role === 'student' ? 'var(--student-bg)' : 'var(--volunteer-bg)';
  const fg = role === 'student' ? 'var(--student-fg)' : 'var(--volunteer-fg)';
  const text = role === 'student' ? '学员' : '志愿者';
  return (
    <Tag
      style={{
        background: bg,
        color: fg,
        border: 'none',
        borderRadius: 10,
        padding: '2px 10px',
        fontSize: 11,
        fontWeight: 600,
        margin: 0,
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        lineHeight: 1.4,
      }}
    >
      {icon}
      {text}
    </Tag>
  );
}

// ---------------------------------------------------------------------------
// 工具
// ---------------------------------------------------------------------------

function clampPercent(n: number): number {
  if (Number.isNaN(n)) return 0;
  if (n < 0) return 0;
  if (n > 100) return 100;
  return n;
}

// 类型守卫占位（避免 noUnusedLocals；同时确认 StatusKey 与 CampStatus 关联）
function _statusTypeguard(_: CampStatus): StatusKey | null {
  const map: Record<CampStatus, StatusKey> = {
    not_started: 'not_started',
    ongoing: 'ongoing',
    ended: 'ended',
  };
  return map[_] ?? null;
}
export { _statusTypeguard };
