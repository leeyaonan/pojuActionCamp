import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  Card,
  Row,
  Col,
  Button,
  Spin,
  Empty,
  Tabs,
  Input,
  Table,
  Tag,
  Tooltip,
  App as AntApp,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { SyncOutlined, SearchOutlined, EditOutlined, FileTextOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { useCamp } from '@/hooks/useCamps';
import { useStudents, useSyncBoard, usePendingGrades } from '@/hooks/useVolunteer';
import type { StudentStatus, StudentSummary } from '@/api/types';

/**
 * P6 志愿者·学员看板（design.md 6.P6 + ui-prototype #volunteer-dashboard）。
 *
 * 页面结构：
 * 1. 页头：标题「学员看板」+ 志愿者徽章 + 营名 + 上次同步时间 +
 *    「⏱ 定时同步」标签 + 「🔄 立即同步」主按钮。
 * 2. 统计 4 卡：带教学员 / 待评改（warn）/ 今日已打卡 / 打卡不足需提醒（danger）。
 * 3. Tab 行：全部 / 待评改 / 打卡不足 / 已评改（带数量徽章）+ 搜索框。
 * 4. 学员表格：昵称 / 已打卡 Day / 有效天数 / 距目标 / 最近星级 / 状态 / 操作。
 *
 * 数据源：
 * - useCamp(campId)         营基本信息（名称 / 起止 / 总天数）
 * - useStudents(campId, status) 学员列表（按 status 筛选；切 Tab 重查）
 * - usePendingGrades(campId) 待评改列表（用于统计「待评改」数量）
 * - useSyncBoard(campId)    手动同步 mutation（成功后 invalidate students）
 */
export default function VolunteerDashboard() {
  const params = useParams<{ id: string }>();
  const campId = params.id ? Number(params.id) : undefined;

  // 营详情（用于副标题与营名）
  const { data: camp, isLoading: campLoading } = useCamp(campId);
  // 待评改列表（用于统计「待评改」数量与今日打卡近似值）
  const { data: pendingGrades } = usePendingGrades(campId);

  // 当前 Tab：'all' | 'pending' | 'insufficient' | 'graded'
  const [tab, setTab] = useState<TabKey>('all');
  // 学员昵称搜索（前端过滤）
  const [searchText, setSearchText] = useState('');

  // 根据 tab 决定传给 useStudents 的 status（map 到后端 StudentStatus）
  const studentStatus = useMemo<StudentStatus | undefined>(() => {
    if (tab === 'pending') return 'ongoing';
    if (tab === 'insufficient') return 'unqualified';
    if (tab === 'graded') return 'qualified';
    return undefined;
  }, [tab]);

  const { data: students, isLoading: studentsLoading, refetch } = useStudents(
    campId,
    studentStatus
  );

  // 手动同步
  const syncMut = useSyncBoard(campId ?? -1);
  const { message } = AntApp.useApp();

  // 全部学员（用于 Tab 数量徽章 + 统计）
  const { data: allStudents } = useStudents(campId);

  // 四个 Tab 的数量（来自不带筛选的列表）
  const counts = useMemo(() => {
    const list = allStudents ?? [];
    return {
      all: list.length,
      pending: list.filter((s) => s.status === 'ongoing').length,
      insufficient: list.filter((s) => s.status === 'unqualified').length,
      graded: list.filter((s) => s.status === 'qualified').length,
    };
  }, [allStudents]);

  // 统计卡：今日已打卡近似 = 待评改数 + 已评改有效数（已存在今日提交但未评改 / 已评改）
  const todayCheckedInCount = useMemo(() => {
    const list = allStudents ?? [];
    // 进行中 / 已达标（已提交了今日）都算已打卡
    return list.filter((s) => s.status !== 'unqualified' || hasPendingToday(s, pendingGrades)).length;
  }, [allStudents, pendingGrades]);

  // 同步处理
  const handleSync = async () => {
    if (!campId) return;
    try {
      const res = await syncMut.mutateAsync();
      if (res.success) {
        message.success(res.message || '同步成功');
        refetch();
      } else {
        message.warning(res.message || '同步未完成');
      }
    } catch {
      // 错误已由 hook 内的 toastOnBizError 处理
    }
  };

  // 搜索过滤后的学员列表
  const filteredStudents = useMemo(() => {
    if (!students) return [];
    const kw = searchText.trim().toLowerCase();
    if (!kw) return students;
    return students.filter(
      (s) => s.nickname.toLowerCase().includes(kw) || (s.wechat ?? '').toLowerCase().includes(kw)
    );
  }, [students, searchText]);

  // 最近一次同步时间（取列表中最新一条 last_synced_at）
  const lastSyncedAt = useMemo(() => {
    const list = allStudents ?? [];
    const times = list
      .map((s) => s.last_synced_at)
      .filter((t): t is string => !!t)
      .sort()
      .reverse();
    return times[0] ?? null;
  }, [allStudents]);

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

  const syncDescText = `带教 ${camp.total_days} 天学员 · 上次同步 ${
    lastSyncedAt ? dayjs(lastSyncedAt).format('MM/DD HH:mm') : '尚未同步'
  }`;

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
            学员看板{' '}
            <span
              style={{
                background: 'var(--volunteer-bg)',
                color: 'var(--volunteer-fg)',
                borderRadius: 10,
                padding: '2px 10px',
                fontSize: 11,
                fontWeight: 600,
                marginLeft: 6,
                verticalAlign: 'middle',
              }}
            >
              志愿者
            </span>
          </h2>
          <div style={{ color: 'var(--text-sub)', fontSize: 13, marginTop: 4 }}>
            {camp.name} · {syncDescText}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <Tooltip title="每日 09:00 自动调用破局读接口拉取最新打卡数据">
            <Tag
              icon={<span style={{ marginRight: 2 }}>⏱</span>}
              style={{
                background: '#f3f4f6',
                color: 'var(--text-sub)',
                border: 'none',
                borderRadius: 10,
                padding: '2px 10px',
                fontSize: 11,
                fontWeight: 600,
                margin: 0,
              }}
            >
              定时同步：每日 09:00
            </Tag>
          </Tooltip>
          <Button
            type="primary"
            icon={<SyncOutlined />}
            loading={syncMut.isPending}
            onClick={handleSync}
          >
            立即同步
          </Button>
        </div>
      </div>

      {/* ============ 统计 4 卡 ============ */}
      <Row gutter={[14, 14]} style={{ marginBottom: 20 }}>
        <Col xs={24} sm={12} md={6}>
          <StatCard primary={counts.all} label="带教学员" hint={`营 ${camp.name}`} />
        </Col>
        <Col xs={24} sm={12} md={6}>
          <StatCard
            primary={<span style={{ color: 'var(--warning)' }}>{counts.pending}</span>}
            label="待评改"
            hint="已提交等待志愿者评改"
          />
        </Col>
        <Col xs={24} sm={12} md={6}>
          <StatCard
            primary={todayCheckedInCount}
            label="今日已打卡"
            hint="含待评改 + 已评改"
          />
        </Col>
        <Col xs={24} sm={12} md={6}>
          <StatCard
            primary={
              <span style={{ color: counts.insufficient > 0 ? 'var(--danger)' : undefined }}>
                {counts.insufficient}
              </span>
            }
            label="打卡不足需提醒"
            hint={counts.insufficient > 0 ? '请主动联系' : '当前无落后学员'}
          />
        </Col>
      </Row>

      {/* ============ 学员表格卡 ============ */}
      <Card style={{ borderRadius: 10 }} bodyStyle={{ padding: 16 }}>
        {/* Tab + 搜索 */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: 12,
            flexWrap: 'wrap',
            gap: 12,
          }}
        >
          <Tabs
            activeKey={tab}
            onChange={(k) => setTab(k as TabKey)}
            items={[
              { key: 'all', label: `全部 ${counts.all}` },
              { key: 'pending', label: `待评改 ${counts.pending}` },
              { key: 'insufficient', label: `打卡不足 ${counts.insufficient}` },
              { key: 'graded', label: `已评改 ${counts.graded}` },
            ]}
            style={{ marginBottom: -16 }}
          />
          <Input
            allowClear
            prefix={<SearchOutlined style={{ color: 'var(--text-light)' }} />}
            placeholder="搜索学员昵称 / 微信"
            style={{ width: 240 }}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
          />
        </div>

        {/* 表格 */}
        <StudentTable
          loading={studentsLoading}
          data={filteredStudents}
          campId={campId}
          minDays={camp.min_checkin_days}
        />
        <div style={{ fontSize: 12, color: 'var(--text-light)', marginTop: 12 }}>
          显示 {filteredStudents.length} / {students?.length ?? 0} 名学员
        </div>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 子组件
// ---------------------------------------------------------------------------

type TabKey = 'all' | 'pending' | 'insufficient' | 'graded';

interface StatCardProps {
  primary: React.ReactNode;
  label: string;
  hint?: string;
}

/** 统计卡（design.md 4.5 stat：大数字 + 标签）。 */
function StatCard({ primary, label, hint }: StatCardProps) {
  return (
    <Card style={{ borderRadius: 10, height: '100%' }} bodyStyle={{ padding: 16 }}>
      <div style={{ fontSize: 26, fontWeight: 700, lineHeight: 1.2 }}>{primary}</div>
      <div style={{ fontSize: 12, color: 'var(--text-sub)', marginTop: 4 }}>{label}</div>
      {hint && (
        <div style={{ fontSize: 11, color: 'var(--text-light)', marginTop: 6 }}>{hint}</div>
      )}
    </Card>
  );
}

interface StudentTableProps {
  loading: boolean;
  data: StudentSummary[];
  campId: number | undefined;
  minDays: number;
}

/** 学员表格：根据 status 派生徽章颜色与距目标文案。 */
function StudentTable({ loading, data, campId, minDays }: StudentTableProps) {
  const columns: ColumnsType<StudentSummary> = [
    {
      title: '学员',
      dataIndex: 'nickname',
      key: 'nickname',
      width: 140,
      render: (nick: string, row) => (
        <div>
          <div style={{ fontWeight: 600 }}>{nick}</div>
          {row.wechat && (
            <div style={{ fontSize: 11, color: 'var(--text-light)' }}>{row.wechat}</div>
          )}
        </div>
      ),
    },
    {
      title: '已打卡',
      dataIndex: 'current_day',
      key: 'current_day',
      width: 90,
      render: (day: number | null | undefined) =>
        day == null ? <span style={{ color: 'var(--text-light)' }}>—</span> : `Day${day}`,
    },
    {
      title: '有效天数',
      key: 'valid_days',
      width: 110,
      render: (_: unknown, row) => (
        <span>
          {row.valid_days} <span style={{ color: 'var(--text-light)' }}>/ {minDays}</span>
        </span>
      ),
    },
    {
      title: '距目标',
      key: 'gap',
      width: 130,
      render: (_: unknown, row) => {
        const gap = row.gap_to_min;
        if (gap <= 0) {
          return (
            <span style={{ color: 'var(--success)' }}>
              已达标（超 {-gap}）
            </span>
          );
        }
        const isInsufficient = row.status === 'unqualified';
        return (
          <span
            style={{
              color: isInsufficient ? 'var(--danger)' : 'var(--text)',
            }}
          >
            差 {gap}
            {isInsufficient && <span style={{ marginLeft: 6 }}>⚠</span>}
          </span>
        );
      },
    },
    {
      title: '最近星级',
      dataIndex: 'last_stars',
      key: 'last_stars',
      width: 110,
      render: (stars: number | null | undefined) =>
        stars == null ? (
          <span style={{ color: 'var(--text-light)' }}>—</span>
        ) : (
          <Stars stars={stars} />
        ),
    },
    {
      title: '状态',
      key: 'status',
      width: 110,
      render: (_: unknown, row) => <StatusBadge status={row.status} />,
    },
    {
      title: '操作',
      key: 'actions',
      width: 180,
      render: (_: unknown, row) => (
        <div style={{ display: 'flex', gap: 6 }}>
          {row.status === 'ongoing' ? (
            <Link to={`/camp/${campId}/volunteer/grade?camp=${campId}&student=${row.id}`}>
              <Button type="primary" size="small" icon={<EditOutlined />}>
                去评改
              </Button>
            </Link>
          ) : (
            <Link to={`/camp/${campId}/volunteer/archive/${row.id}`}>
              <Button size="small" icon={<FileTextOutlined />}>
                查看档案
              </Button>
            </Link>
          )}
          {/* 已达标 / 未达标也可点击档案查看完整历史 */}
          {row.status === 'ongoing' && (
            <Link to={`/camp/${campId}/volunteer/archive/${row.id}`}>
              <Button size="small">档案</Button>
            </Link>
          )}
        </div>
      ),
    },
  ];

  if (!loading && data.length === 0) {
    return <Empty description="该筛选下暂无学员" style={{ padding: '32px 0' }} />;
  }

  return (
    <Table<StudentSummary>
      rowKey="id"
      loading={loading}
      dataSource={data}
      columns={columns}
      pagination={false}
      size="middle"
    />
  );
}

/** 星级渲染（金色实心 + 灰色空心）。 */
function Stars({ stars }: { stars: number }) {
  return (
    <span style={{ color: 'var(--star)', letterSpacing: 1 }}>
      {'★'.repeat(Math.max(0, Math.min(3, stars)))}
      <span style={{ color: 'var(--text-light)' }}>
        {'☆'.repeat(Math.max(0, 3 - stars))}
      </span>
    </span>
  );
}

/** 状态徽章（映射 StudentStatus → 颜色与文案）。 */
function StatusBadge({ status }: { status: StudentStatus }) {
  if (status === 'ongoing') return <Tag color="orange">待评改</Tag>;
  if (status === 'unqualified') return <Tag color="red">打卡不足</Tag>;
  if (status === 'qualified') return <Tag color="green">已评改</Tag>;
  return <Tag>{status}</Tag>;
}

// ---------------------------------------------------------------------------
// 工具函数
// ---------------------------------------------------------------------------

/**
 * 判断学员是否今日已提交打卡（用于「今日已打卡」统计近似）。
 *
 * 后端 StudentSummary 不直接含「今日是否已打卡」字段，故借助 usePendingGrades
 * 推导：若该学员出现在待评改列表中，则视为今日已提交；否则按状态粗略推断。
 */
function hasPendingToday(
  student: StudentSummary,
  pendingGrades: { student_id: number }[] | undefined
): boolean {
  if (!pendingGrades) return false;
  return pendingGrades.some((p) => p.student_id === student.id);
}